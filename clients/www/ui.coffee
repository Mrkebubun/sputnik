$ ->
    location = window.location
    hostname = location.hostname
    protocol = location.protocol
    if protocol == 'http:'
        ws_protocol = "ws:"
    else
        ws_protocol = "wss:"

    uri = ws_protocol + "//" + hostname + ":8000"
    # REMOVE THIS IF NOT TESTING VS DEMO
    uri = "wss://demo.m2.io:8000"

    window.my_audit_hash = ''
    window.contract = ''
    window.contract_type = 'cash_pair'
    window.markets = {}
    window.margin = [0, 0]
    window.ohlcv_period = "day"
    window.orders = []

    sputnik = new Sputnik uri
    window.sputnik = sputnik

    $.ajax {
            url: 'index_template.html'
            success: (data, status, xhr) ->
                start(data)
            }

    start = (template) ->
        ractive = new Ractive
            el: "target"
            template: template
            data:
                sputnik: sputnik
                current_ticker: null
                current_type: "cash_pair"
                type_alias:
                    "cash_pair": "Cash"
                    "prediction": "Predictions"
                    "futures": "Futures"
                format_time: (datetime) ->
                    if datetime?
                        new Date(datetime/1000).toLocaleString()
            adapt: [Ractive.adaptors.Sputnik]
            debug: true

        ractive.on
            switch_type: (event, type) ->
                ractive.set "current_type", type

            switch_contract: (event) ->
                ractive.set "current_ticker", event.context

        ractive.observe "current_ticker", (new_ticker, old_ticker, path) ->
            if old_ticker?
                sputnik.unfollow old_ticker
            if new_ticker?
                window.contract = new_ticker
                sputnik.openMarket new_ticker
                #showChart new_ticker
                #updateContract()
                #updateBalances()
                #updateOrders()

        window.ractive = ractive

        sputnik.connect()

        tv = new window.TVFeed sputnik
        window.tv = tv

        sputnik.on "log", (args...) -> ab.log args...
        sputnik.on "warn", (args...) -> ab.log args...
        sputnik.on "error", (args...) -> ab.log args...

        sputnik.on "open", () ->
            sputnik.log "open"
            $('#main_page').show()
            $('#not_connected').hide()

            # Hide not-logged in stuff
            $('#account-btn').hide()
            $('#contract-balances,#buy-sell-orders').hide()
            $('#logged_in').hide()
            #$('#contract').hide()

            # Hide stuff by default
            for page in ['trade', 'account']
                $("#page-#{page}").hide()

            # Attempt a cookie login
            cookie = document.cookie
            sputnik.log "cookie: #{cookie}"
            if cookie
                parts = cookie.split("=", 2)[1].split(":", 2)
                name = parts[0]
                uid = parts[1]
                if !uid
                    document.cookie = ''
                else
                    sputnik.restoreSession uid

        sputnik.on "auth_success", (username) ->
            ladda = Ladda.create $("#login_button")[0]
            ladda.stop()
            $("#login_modal").modal "hide"
            ladda = Ladda.create $("#register_button")[0]
            ladda.stop()
            $("#register_modal").modal "hide"

            $("#login-div").hide()
            $("#login_name").text username
            #$("#acct_management_username").val username
            $("#logged_in").show()

            $('#account-btn').show()

            $("#contract-balances,#buy-sell-orders").fadeIn()
            sputnik.getCookie()

        sputnik.on "cookie", (uid) ->
            sputnik.log "cookie: " + uid
            document.cookie = "login" + "=" + sputnik?.username + ":" + uid

        sputnik.on "auth_fail", (error) ->
            ladda = Ladda.create $("#login_button")[0]
            ladda.stop()
            $("#login_error").text("Incorrect username or password.").show()

        sputnik.on "make_account_success", () ->
            # do not clear the modal yet, do it in auth_success
            username = $("#register_username").val()
            password = $("#register_password").val()
            sputnik.authenticate username, password

        sputnik.on "make_account_fail", (event) ->
            ladda = Ladda.create $("#register_button")[0]
            ladda.stop()
            [code, reason] = event
            $("#register_error").text(reason)
            $("#register_error").show()

        # compropago modal success and error
        sputnik.on "compropago_deposit_success", (event) ->
          ladda = Ladda.create $("#compropago_pay_button")[0]
          ladda.stop()

          $('#compropago_confirm').text(event['note_confirmation'])
          $('#compropago_step_1').text(event['step_1'])
          $('#compropago_step_2').text(event['step_2'])
          $('#compropago_step_3').text(event['step_3'])
          $('#compropago_expiration').text(event['note_expiration_date'])
          $('#compropago_comition').text(event['note_extra_comition'])
          $('#compropago_modal').modal 'hide'
          $('#compropago_confirm_modal').modal 'show'

        sputnik.on "compropago_deposit_fail", (event) ->
          ladda = Ladda.create $('#compropago_pay_button')[0]
          ladda.stop()
          [code, reason] = event
          $('#compropago_error').text(reason)
          $('#compropago_error').show()

        $("#login").click () ->
            $("#login_modal").modal()

        $("#login_modal").keypress (e) -> $("#login_button").click() if e.which is 13

        $("#login_button").click (event) ->
            event.preventDefault()

            username = $("#login_username").val()
            password = $("#login_password").val()

            $("#login_error").hide()
            ladda = Ladda.create $("#login_button")[0]
            ladda.start()
            sputnik.authenticate username, password
            $('#login_modal .alert:visible').hide()

        $("#register").click () ->
            $("#register_modal").on('hidden.bs.modal', -> $('#register_error').hide())
            $("#register_modal").modal()

        $("#register_button").click (event) ->
            event.preventDefault()

            username = $("#register_username").val()
            password = $("#register_password").val()
            email = $("#register_email").val()
            nickname = $("#register_nickname").val()
            eula = $("#register_eula").is(":checked")

            if username and password and email and nickname and eula
                $('#register_error').hide()
                ladda = Ladda.create $("#register_button")[0]
                ladda.start()
                sputnik.makeAccount username, password, email, nickname
            else
                $('#register_error').text('Please complete the registration form and accept the terms and conditions to continue.').slideDown()

        withinAnOrderOfMagnitude = (x, y) ->
            sign = (number) -> if number then (if number < 0 then -1 else 1) else 0
            orderOfMag = (w) ->  sign(w) * Math.ceil(Math.log(Math.abs(w) + 1) / Math.log(10))
            orderOfMag(x) == orderOfMag(y)

        $("#buy_price,#buy_quantity").keyup ->
            if not sputnik.canPlaceOrder(Number($("#buy_quantity").val()), Number($("#buy_price").val()), window.contract, 'BUY')
                $("#buy_alert").show()
            else
                $("#buy_alert").hide()

        $("#sell_price,#sell_quantity").keyup ->
            if not sputnik.canPlaceOrder(Number($("#sell_quantity").val()), Number($("#sell_price").val()), window.contract, 'SELL')
                $("#sell_alert").show()
            else
                $("#sell_alert").hide()

        $("#buyButton").click ->
            buy_quantity = Number($('#buy_quantity').val())
            buy_price = Number($("#buy_price").val())

            if buy_quantity == 0 or buy_price == 0
                return true

            if not withinAnOrderOfMagnitude(buy_price, window.markets[window.contract].best_ask.price)
                bootbox.confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?', (result) ->
                    if result
                        sputnik.placeOrder(buy_quantity, buy_price, window.contract, 'BUY')
            else
                sputnik.placeOrder(buy_quantity, buy_price, window.contract, 'BUY')

        $("#sellButton").click ->
            sell_quantity = Number($('#sell_quantity').val())
            sell_price = Number($("#sell_price").val())

            if sell_quantity == 0 or sell_price == 0
                return true

            if not withinAnOrderOfMagnitude(sell_price, window.markets[window.contract].best_bid.price)
                bootbox.confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?', (result) ->
                    if result
                        sputnik.placeOrder(sell_quantity, sell_price, window.contract, 'SELL')
            else
                sputnik.placeOrder(sell_quantity, sell_price, window.contract, 'SELL')

        $("#logout").click (event) ->
            document.cookie = ''
            sputnik.logout()
            location.reload()

        showTrades = (e) ->
            e.preventDefault()
            $('#trades').show()
            $('#trades-btn').addClass('active-link-box-sml')
            $('#trades-btn').removeClass('inactive-link-box-sml')

            $('#book').hide()
            $('#book-btn').addClass('inactive-link-box-sml')
            $('#book-btn').removeClass('active-link-box-sml')

        showBook = (e) ->
            e.preventDefault()
            $('#book').show()
            $('#book-btn').addClass('active-link-box-sml')
            $('#book-btn').removeClass('inactive-link-box-sml')

            $('#trades').hide()
            $('#trades-btn').addClass('inactive-link-box-sml')
            $('#trades-btn').removeClass('active-link-box-sml')

        $('#trades-btn').click showTrades
        $('#book-btn').click showBook

        $('#trades-book-select').change (e) ->
            if $('#trades-book-select').val() == 'trades'
                showTrades(e)
            else
                showBook(e)

        $("#save_changes_button").click (event) ->
            if $('#change_password_tab').data('dirty')
                if $('#new_password').val() is $('#new_password_confirm').val()
                    bootbox.alert "Passwords do not match"
                else
                    sputnik.changePassword $('#old_password').val(), $('#new_password_confirm').val()

            if $('#user_information_tab').data('dirty')
                sputnik.changeProfile($('#new_nickname').val(), $('#new_email').val())

            if $('#compliance_tab').data('dirty')
                $('#compliance_tab form').submit (e)->
                    e.preventDefault()
                    compliance_client_handler($('#compliance_tab form').eq(0))
                $('#compliance_tab form').submit()

            $('#account_modal .tab-pane').data('dirty', no)

        $("#compropago_pay_button").click (event) ->
            event.preventDefault()
            ladda = Ladda.create $("#compropago_pay_button")[0]
            ladda.start()
            store = $("#compropago_store").val()
            amount = $("#compropago_amount").val()
            send_sms = $("#compropago_send_sms").is(":checked")
            customer_email = $('#compropago_email').val()
            customer_phone = $('#compropago_phone').val()
            customer_phone_company = $('#compropago_phone_company').val()

            if (Number(amount) < 6000)
              sputnik.makeCompropagoDeposit store, Number(amount), customer_email, send_sms, customer_phone, customer_phone_company

        $('#chatButton').click ->
            chat_return = sputnik.chat chatBox.value
            if not chat_return[0]
                bootbox.alert chat_return[1]

            $('#chatBox').val('')

        showChart = (contract) ->
            widget = new TradingView.widget {
                fullscreen: false
                symbol: contract
                interval: "D"
                toolbar_bg: '#f4f7f9'
                allow_symbol_change: false
                container_id: "tv_chart_container"
                datafeed: window.tv
                library_path: "charting_library/"
                locale: "en"
                autosize: true
                theme: "White"
                style: "2"
                hideideas: true
                hide_top_toolbar: true
                withdateranges: true
                details: false
                save_image: false
                show_popup_button: false
                # Regression Trend-related functionality is not implemented yet, so it's hidden for a while
                disabled_drawings: ["Regression Trend"]
            }

            widget.onChartReady () ->
                sputnik.log("onChartReady")
                $("#tv_chart_container iframe").contents().find(".tv-side-toolbar").hide()

        changeContractType = (new_type) ->
            if new_type != window.contract_type
                $("#tab-#{window.contract_type}").removeClass("tab-active")
                $("#tab-#{window.contract_type}").addClass("tab-inactive")
                $("#tab-#{new_type}").addClass("tab-active")
                $("#tab-#{new_type}").removeClass("tab-inactive")
                window.contract_type = new_type
                window.contract = ''
                ractive.set "current_type", new_type

        $('#cash_pair-btn').click ->
            changeContractType('cash_pair')

        $('#futures-btn').click ->
            changeContractType('futures')

        $('#prediction-btn').click ->
            changeContractType('prediction')

        $('#account_modal').change (e) ->
            $(e.target).parents('.tab-pane').data('dirty', yes)

        $('#get_reset_token').click ->
            username = $("#login_username").val()
            $('#login_modal .alert:visible').hide()

            if username.length < 4
                $('#login_error').text("Please enter a username to reset the password").slideDown()
                return

    #        $('#login_modal').find('input,a,label,button').slideUp()
            sputnik.getResetToken(username)
            $('#reset_token_sent').show()
            setTimeout(
                ->
                    $('#login_modal .alert:visible').hide()
                    $("#login_modal").modal "hide"
            ,
            5000)

        $("#account").click ->
            $("#account_modal").modal()

        $("#transactions").click ->
            $("#transactions_modal").modal()
            $("#transactions_button").click ->
                sputnik.log ["get_history", $("#transactions_start_date").val(), $("#transactions_end_date").val()]
                start_timestamp = Date.parse($("#transactions_start_date").val()) * 1000
                end_timestamp = Date.parse($("#transactions_end_date").val()) * 1000
                sputnik.getTransactionHistory(start_timestamp, end_timestamp)

        $("#audit").click ->
            $("#audit_modal").modal()
            sputnik.getAudit()

        $('#contract_list').change ->
            if $('#contract_list').val() != window.contract
                sputnik.unfollow window.contract
                window.contract = $('#contract_list').val()
                sputnik.openMarket window.contract

        sputnik.on "change_password_token", (args) ->
            $('#change_password_token_modal').modal "show"

        sputnik.on "change_password_fail", (err) -> #BUG: this is not firing multiple times
            console.log "[mexbt:15 - hit error]"
            $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-danger').text("Error: #{err[1]}")

        $("#change_password_token_button").click ->
            console.log "[mexbt:15 - hit!]"
            if $('#new_password_token').val() == $('#new_password_token_confirm').val()
                sputnik.changePasswordToken($('#new_password_token').val())
            else
                $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-danger').text "Passwords do not match"

        sputnik.on "change_password_success", ->
            $('#change_password_token_modal').find('input,a,label,button').slideUp()
            $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-success').text('Password reset')
            setTimeout(
                ->
                    $('#change_password_token_modal').modal "hide"
            ,
                5000)

        sputnik.on "markets", (markets) ->
            for ticker, details of markets
                window.markets[ticker] = details
                window.markets[ticker].best_ask = {price: Infinity, quantity: 0}
                window.markets[ticker].best_bid = {price: 0, quantity: 0}
                window.markets[ticker].position = 0

        sputnik.on "session_expired", ->
            console.log "Session is stale."
            document.cookie = ''

        sputnik.on "positions", (positions) ->
            for ticker, position of positions
                if @markets[ticker].contract_type != "cash_pair"
                    window.markets[ticker].position = position.position

            updateBalances()

        updateContract = () ->
            if window.contract_type != "cash_pair"
                $("#contract-expiration").show()
            else
                $("#contract-expiration").hide()

            $("#contract-description").text window.markets[window.contract].description

        updateBalances = () ->
            if window.contract_type != "cash_pair"
                $("#btc_balance").text window.markets['BTC'].position.toFixed(sputnik.getQuantityPrecision('BTC'))
                $("#btc_balance").attr('data-original-title', window.markets['BTC'].position).tooltip('fixTitle')
                $("#contract_balance").text window.markets[window.contract].position.toFixed(sputnik.getQuantityPrecision(window.contract))
                $("#contract_balance").attr('data-original-title', window.markets[window.contract].position).tooltip('fixTitle')
                $("#contract_ticker").text window.contract
                $("#low_margin").text window.margin[0].toFixed(sputnik.getQuantityPrecision('BTC'))
                $("#high_margin").text window.margin[1].toFixed(sputnik.getQuantityPrecision('BTC'))
                $("#low_margin").attr('data-original-title', window.margin[0]).tooltip('fixTitle')
                $("#high_margin").attr('data-original-title', window.margin[1]).tooltip('fixTitle')
                $("#margin-balance").show()
                $("#cash_pair-balance").hide()
            else
                denominated_contract = window.markets[window.contract].denominated_contract_ticker
                denominated_position = window.markets[denominated_contract].position

                payout_contract = window.markets[window.contract].payout_contract_ticker
                payout_position = window.markets[payout_contract].position

                $("#payout_balance").text payout_position.toFixed(sputnik.getQuantityPrecision(payout_contract))
                $("#payout_ticker").text payout_contract
                $("#payout_balance").attr('data-original-title', payout_position).tooltip('fixTitle')

                $("#denominated_ticker").text denominated_contract
                $("#denominated_balance").text denominated_position.toFixed(sputnik.getQuantityPrecision(denominated_contract))
                $("#denominated_balance").attr('data-original-title', denominated_position).tooltip('fixTitle')

                $("#margin-balance").hide()
                $("#cash_pair-balance").show()

    #    We are disabling chat for now in the UI because we didn't make space for it
    #    sputnik.on "chat_history", (chat_messages) ->
    #        $('#chatArea').html(chat_messages.join("\n"))
    #        $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight)
    #
    #    sputnik.on "chat", (chat) ->
    #        $.growl({title: "Chat", message: chat})

        sputnik.on "address", (info) ->
            ticker = info[0]
            address = info[1]
            $("##{ticker}_deposit_address").attr('href', 'bitcoin:' + address).text(address)
            $("##{ticker}_deposit_qrcode").empty()
            $("##{ticker}_deposit_qrcode").qrcode("bitcoin:" + address)

        sputnik.on "address_fail", (error) ->
            bootbox.alert "Deposit address error: #{error[1]}"

        sputnik.on "deposit_instructions", (event) ->
            ticker = event[0]
            instructions = event[1]
            $("##{ticker}_deposit_instructions").text instructions

        $("#ohlcv_period").change () ->
            window.ohlcv_period = $("#ohlcv_period").value
            $('#low').text 'N/A'
            $('#high').text 'N/A'
            $('#vwap').text 'N/A'

        sputnik.on "ohlcv", (ohlcv) ->
            sputnik.log ["ohlcv received", ohlcv]
            if ohlcv.contract == window.contract
                if ohlcv.period == "minute"
                    window.chart.dataSets[0].dataProvider.push {
                        open: ohlcv.open,
                        close: ohlcv.close,
                        high: ohlcv.high,
                        low: ohlcv.low,
                        volume: ohlcv.volume,
                        date: ohlcv.wire_open_timestamp/1000
                    }
                else if ohlcv.period == window.ohlcv_period
                    $('#low').text ohlcv.low.toFixed(precision)
                    $('#high').text ohlcv.high.toFixed(precision)
                    $('#vwap').text ohlcv.vwap.toFixed(precision)

        sputnik.on "ohlcv_history", (ohlcv_history) ->
            sputnik.log ["ohlcv_history", ohlcv_history]
            keys = Object.keys(ohlcv_history)
            if keys.length
                last_key = keys[keys.length-1]
                last_entry = ohlcv_history[last_key]
                precision = sputnik.getPricePrecision(window.contract)
                if last_entry.period == window.ohlcv_period
                    if last_entry.contract == window.contract
                        $('#low').text last_entry.low.toFixed(precision)
                        $('#high').text last_entry.high.toFixed(precision)
                        $('#vwap').text last_entry.vwap.toFixed(precision)
            else
                $('#low').text 'N/A'
                $('#high').text 'N/A'
                $('#vwap').text 'N/A'

        sputnik.on "password_change_success", (info) ->
            bootbox.alert "Password successfully changed"

        sputnik.on "password_change_fail", (error) ->
            bootbox.alert "Password change fail: #{error}"

        sputnik.on "request_withdrawal_success", (info) ->
            bootbox.alert "Withdrawal request placed"

        sputnik.on "request_withdrawal_fail", (error) ->
            bootbox.alert "Withdrawal request failed: #{error[1]}"

        sputnik.on "place_order_fail", (error) ->
            bootbox.alert "order placement failed: #{error[1]}"

        sputnik.on "profile", (profile) ->
            $('#new_nickname').val profile.nickname
            $('#new_email').val profile.email

        sputnik.on "audit_details", (audit) ->
            $('#audit_timestamp').text audit.timestamp
            for account_type in ['assets', 'liabilities']
                $output = []
                $output.push '<ul class="nav nav-tabs">'
                for own currency_code, currency of audit[account_type]
                    $output.push '<li><a href="#' + account_type + '_' + currency_code + '" data-toggle="tab">' + currency_code + '</a></li>'

                $output.push '</ul>'

                $output.push '<div class="tab-content">'
                for own currency_code, currency of audit[account_type]
                    $output.push '<div class="tab-pane" id="' + account_type + '_' + currency_code + '">'

                    $output.push('<table id="audit_' + account_type + '_' + currency_code +
                        '" class="table table-hover table-bordered table-condensed"><thead><tr><th>ID</th><th class="text-right">Amount</th></tr></thead><tbody>')
                    #Positions
                    for position in currency.positions
                        audit_hash = position[0]

                        audit_amount = position[1].toFixed(sputnik.getQuantityPrecision(currency_code))

                        row_class = ''
                        if audit_hash is my_audit_hash
                            row_class = "class='alert-success'"

                        $output.push("<tr #{row_class}><td>#{audit_hash}</td>" +
                            "<td class='text-right'>#{audit_amount}</td></tr>")
                    #Total
                    currency_total = currency.total.toFixed(sputnik.getQuantityPrecision(currency_code))

                    $output.push "</tbody><tfoot><tr class=\"alert-info\"><td><strong>Total</strong></td><td class='text-right'><strong>#{currency_total}</strong></td></tr></tfoot></table>"
                    $output.push "</div>"

                $output.push '</div>'
                html = $output.join('')
                console.log "[ui:426 - html]", html
                $("#audit_#{account_type}").html(html)

        sputnik.on "audit_hash", (audit_hash) ->
            window.my_audit_hash = audit_hash
            $('#audit_hash').text audit_hash

        sputnik.on "transaction_history", (transaction_histories) ->
            html = []
            for his in transaction_histories
                trHTML = "<tr><td>#{his['timestamp']}</td>
                     <td>#{his['type'] ? ''}</td>
                     <td>#{his['contract'] ? ''}</td>
                     <td class='text-right'>#{his['quantity'] ? 'X'}</td></tr>"
                html.push(trHTML)
            $('#transaction_history tbody').html(html.join())

        sputnik.on "margin", (margin) ->
            window.margin = margin
            updateBalances()

        sputnik.on "fill", (fill) ->
            quantity_fmt = fill.quantity.toFixed(sputnik.getQuantityPrecision(fill.contract))
            price_fmt = fill.price.toFixed(sputnik.getPricePrecision(fill.contract))
            $.growl.notice { title: "Fill", message: "#{fill.contract}:#{fill.side}:#{quantity_fmt}@#{price_fmt}" }

        sputnik.on "close", (message) ->
            $('#main_page').hide()
            $('#not_connected').show()

        jQuery.fn.serializeObject = ->
            arrayData = @serializeArray()
            objectData = {}
            $.each arrayData, ->
                if @value?
                    value = @value
                else
                    value = ''
                if objectData[@name]?
                    unless objectData[@name].push
                        objectData[@name] = [objectData[@name]]
                    objectData[@name].push value
                else
                    objectData[@name] = value
            return objectData

        @compliance_client_handler = (form) ->
            sputnik.getRequestSupportNonce 'Compliance', (nonce) ->
              fd = new FormData()
              fd.append('username', $("#login_name").text())
              fd.append('nonce', nonce)
              fd.append('file', form.find('input[name=file]')[0].files[0])
              fd.append('file', form.find('input[name=file]')[1].files[0])
              fd.append('data', JSON.stringify(form.serializeObject()))
              $.ajax
                url: "#{location.origin}/ticket_server/create_kyc_ticket",
                data: fd,
                processData: false,
                contentType: false,
                type: 'POST',
                success: (data) ->
                    bootbox.alert("Successfully saved:" + data)
                error: (err) ->
                    bootbox.alert("Error while saving:" + err)
                    sputnik.log ["Error:", err]

