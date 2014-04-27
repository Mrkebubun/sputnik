location = window.location
hostname = location.hostname
protocol = location.protocol
if protocol == 'http:'
    ws_protocol = "ws:"
else
    ws_protocol = "wss:"

uri = ws_protocol + "//" + hostname + ":8000"

window.best_ask = {price: Infinity, quantity: 0}
window.best_bid = {price: 0, quantity: 0}
window.my_audit_hash = ''
window.contract = 'BTC/HUF'

sputnik = new window.Sputnik uri
window.sputnik = sputnik

sputnik.on "log", (args...) -> ab.log args...
sputnik.on "warn", (args...) -> ab.log args...
sputnik.on "error", (args...) -> ab.log args...

sputnik.on "auth_success", (username) ->
    ladda = Ladda.create $("#login_button")[0]
    ladda.stop()
    $("#login_modal").modal "hide"
    ladda = Ladda.create $("#register_button")[0]
    ladda.stop()
    $("#register_modal").modal "hide"

    $("#login").toggle()
    $("#register").toggle()
    $("#cash_positions").toggle()
    $("#login_name").text username
    $("#acct_management_username").val username
    $("#mxn_balance,#btc_balance,#account_menu,#buy_panel,#sell_panel,#orders_panel").fadeIn()
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

    if (username.length > 3 and password.length > 5)
        $("#login_error").hide()
        ladda = Ladda.create $("#login_button")[0]
        ladda.start()
        sputnik.authenticate username, password
        $('#login_modal .alert:visible').hide()
    else
        $('#login_error').text("Please enter a username and password").slideDown()

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

$("#buy_price,buy_quantity").keyup ->
    if not sputnik.canPlaceOrder(Number($("#buy_quantity").val()), Number($("#buy_price").val()), window.contract, 'BUY')
        $("#buy_panel alert:visible").slideUp()
    else
        $("#buy_panel alert").slideDown()

$("#sell_price,#sell_quantity").keyup ->
    if not sputnik.canPlaceOrder(Number($("#sell_quantity").val()), Number($("#sell_price").val()), window.contract, 'SELL')
        $("#sell_panel alert:visible").slideUp()
    else
        $("#sell_panel alert").slideDown()

$("#buyButton").click ->
    buy_quantity = Number($('#buy_quantity').val())
    buy_price = Number($("#buy_price").val())

    if buy_quantity == 0 or buy_price == 0
        return true

    if not withinAnOrderOfMagnitude(buy_price, best_ask.price)
        return if not confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?'

    sputnik.placeOrder(buy_quantity, buy_price, window.contract, 'BUY')

$("#sellButton").click ->
    sell_quantity = Number($('#sell_quantity').val())
    sell_price = Number($("#sell_price").val())

    if sell_quantity == 0 or sell_price == 0
        return true

    if not withinAnOrderOfMagnitude(sell_price, window.best_bid.price)
        return if not confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?'

    sputnik.placeOrder(sell_quantity, sell_price, window.contract, 'SELL')

$("#logout").click (event) ->
    document.cookie = ''
    sputnik.logout()
    location.reload()


$("#save_changes_button").click (event) ->
    if $('#change_password_tab').data('dirty')
        if $('#new_password').val() is $('#new_password_confirm').val()
            alert "Passwords do not match"
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


$('#new_address_button').click (event) ->
    sputnik.newAddress('BTC')

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
        alert chat_return[1]

    $('#chatBox').val('')

updateTable = (id, data) ->
    rows = for [price, quantity] in data
        "<tr><td>#{price}</td><td>#{quantity}</td></tr>"
    $('#' + "#{id}").html rows.join("")

updateBuys = (data) ->
    updateTable "buys", data

    if not $("#sell_price").is(":focus") and not $("#sell_quantity").is(":focus")
#        _.debounce -> $("#sell_price").val window.best_bid.price
        $("#sell_price").val window.best_bid.price
#            ,
#            500, maxWait: 1000
updateSells = (data) ->
    updateTable "sells", data
    if not $("#buy_price").is(":focus") and not $("#buy_quantity").is(":focus")
#      _.debounce -> $("#buy_price").val window.best_ask.price
        $("#buy_price").val window.best_ask.price
#        ,
#        500, maxWait: 1000
updateTrades = (data) ->
    trades_reversed = data.reverse()
    rows = for trade in trades_reversed[0..20]
        "<tr><td>#{trade.price}</td><td>#{trade.quantity}</td><td>#{trade.timestamp}</td></tr>"
    $("#trades").html rows.join("")

#updatePlot = (data) ->
#    console.log "[ui:238 - UpdatePlot called]"
#    plot_data = for trade in data
#        [trade.wire_timestamp / 1000, trade.price]
#    data =
#        data: plot_data
#        label: 'Trades'
#
#    options =
#        xaxis:
#            mode: 'time'
#            timezone: 'browser'
#            format: '%H:%M:%S'
#
#    $.plot("#lineChart", [data], options)

updateOrders = (orders) ->
    rows = []
    for id, order of orders
        icon = "<span class='label label-warning'>Sell</span>"
        if order.side is "BUY"
            icon = "<span class='label label-primary'>Buy</span>"
        icon = "<td>#{icon}</td>"
        price = "<td>#{order.price}</td>"
        quantity = "<td>#{order.quantity_left}</td>"
        contract = "<td>#{order.contract}</td>"
        #timestamp = "<td>#{order.timestamp}</td>"
        #id = "<td>#{id}</td>"
        button = "<td><button type='button' class='btn btn-danger' onclick='sputnik.cancelOrder(#{id})'>"
        button += "<span class='glyphicon glyphicon-trash'></span>"
        button += "</button></td>"
        rows.push "<tr>" + contract + icon + price + quantity + button + "</tr>"

    $("#orders").html rows.join("")

$ ->
    sputnik.connect()
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
        sputnik.getTransactionHistory()

    $("#audit").click ->
        $("#audit_modal").modal()
        sputnik.getAudit()

    $('#contract_list').change ->
        if $('#contract_list').val() != window.contract
            sputnik.unfollow window.contract
            window.contract = $('#contract_list').val()
            sputnik.openMarket window.contract

    $('#withdraw_BTC_button').click ->
        if $('#withdraw_BTC_address').val() != $('#withdraw_BTC_address_confirm').val()
            alert "Addresses do not match"
        else
            sputnik.requestWithdrawal('BTC', $('#withdraw_BTC_amount').val(), $('#withdraw_BTC_address').val())

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
        contracts_output = []
        positions_output = []

        for ticker, details of markets
            if details.contract_type != "cash"
                if ticker == window.contract
                    contracts_output.push '<option selected value="' + ticker + '">' + ticker + '</option>'
                else
                    contracts_output.push '<option value="' + ticker + '">' + ticker + '</option>'

            if details.contract_type != "cash_pair"
                if details.contract_type == "cash"
                    positions_output.push '<li id="' + ticker + '_balance" class="dropdown pull-right">'
                    positions_output.push '<a href="#" class="dropdown-toggle" style="padding: 15px 10px;" data-toggle="dropdown">'
                    positions_output.push '<b>' + ticker + '<div id="' + ticker + 'pos"></div></b><b class="caret"></b></a>'
                    positions_output.push '<ul class="dropdown-menu">'
                    positions_output.push '<li><a href="#" id="deposit_' + ticker + '">Deposit</a></li>'
                    positions_output.push '<li><a href="#" id="withdraw_' + ticker + '">Withdraw</a></li>'
                    positions_output.push '</ul></li>'
                else
                    positions_output.push '<li id="' + ticker + '_balance" class="pull-right">'
                    positions_output.push '<b style="padding: 15px 10px;">' + ticker + '<div id="' + ticker + 'pos"></div></b>'


            positions_html = positions_output.join('\n')
            contracts_html = contracts_output.join('\n')
            $('#contract_list').html contracts_html
            $('#cash_positions').html positions_html

        # We have to create these click functions after the DOM
        # gets updated
        for ticker, details of markets
            if details.contract_type is "cash"
                deposit_fn = (ticker_to_use) ->
                    (event) ->
                        sputnik.getAddress(ticker_to_use)
                        $("#deposit_#{ticker_to_use}_modal").modal()

                withdraw_fn = (ticker_to_use) ->
                    (event) ->
                        $("#withdraw_#{ticker_to_use}_modal").modal()

                $("#deposit_#{ticker}").click deposit_fn(ticker)
                $("#withdraw_#{ticker}").click withdraw_fn(ticker)

        sputnik.openMarket(window.contract)

sputnik.on "trade_history", (trade_history) ->
    console.log "[ui:383 - hit trade_history]"
    updateTrades(trade_history[window.contract])
    lineChartUpdate(trade_history[window.contract])
    if trade_history[window.contract].length
        $('#last').text trade_history[window.contract][trade_history[window.contract].length - 1].price.toFixed(sputnik.getPricePrecision(window.contract))
    else
        $('#last').text 'N/A'

sputnik.on "open", () ->
    sputnik.log "open"

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

sputnik.on "session_expired", ->
    console.log "Session is stale."
    document.cookie = ''

sputnik.on "book", (book) ->
    if book.contract is not window.contract
        return

    if book.asks.length
        window.best_ask = book.asks[0]
    else
        window.best_ask = {price: Infinity, quantity: 0}

    $('#best_ask').text window.best_ask.price.toFixed(sputnik.getPricePrecision(window.contract))

    if book.bids.length
        window.best_bid = book.bids[0]
    else
        window.best_bid = {price: 0, quantity: 0}

    $('#best_bid').text window.best_bid.price.toFixed(sputnik.getPricePrecision(window.contract))

    updateBuys ([book_row.price, book_row.quantity] for book_row in book.bids)
    updateSells ([book_row.price, book_row.quantity] for book_row in book.asks)

sputnik.on "orders", (orders) ->
    updateOrders orders

sputnik.on "trade", (trade) ->
    if trade.contract == window.contract
        $('#last').text trade.price.toFixed(sputnik.getPricePrecision(window.contract))

sputnik.on "positions", (positions) ->
    for ticker, position of positions
        if @markets[ticker].contract_type != "cash_pair"
            $("##{ticker}pos").text position.position.toFixed(sputnik.getQuantityPrecision(ticker))

sputnik.on "chat", (chat_messages) ->
    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "address", (info) ->
    # We only support BTC here
    address = info[1]
    $('#btc_deposit_address').attr('href', 'bitcoin:' + address).text(address)
    $('#btc_deposit_qrcode').empty()
    $('#btc_deposit_qrcode').qrcode("bitcoin:" + address)

sputnik.on "ohlcv", (ohlcv) ->
    sputnik.log ["ohlcv received", ohlcv]
    if ohlcv.period == "minute"
        ohlcChartUpdate(ohlcv)

sputnik.on "ohlcv_history", (ohlcv_history) ->
    sputnik.log ["ohlcv_history", ohlcv_history]
    keys = Object.keys(ohlcv_history)
    if keys.length
        last_key = keys[keys.length-1]
        last_entry = ohlcv_history[last_key]
        precision = sputnik.getPricePrecision(window.contract)
        if last_entry.period == 'day'
            if last_entry.contract == window.contract
                $('#low').text last_entry.low.toFixed(precision)
                $('#high').text last_entry.high.toFixed(precision)
                $('#vwap').text last_entry.vwap.toFixed(precision)
        else if last_entry.period == 'minute'
            ohlcChartLoad(ohlcv_history)
    else
        $('#low').text 'N/A'
        $('#high').text 'N/A'
        $('#vwap').text 'N/A'

sputnik.on "password_change_success", (info) ->
    alert "Password successfully changed"

sputnik.on "password_change_fail", (error) ->
    alert "Password change fail: #{error}"

sputnik.on "request_withdrawal_success", (info) ->
    alert "Withdrawal request placed"

sputnik.on "request_withdrawal_fail", (error) ->
    alert "Withdrawal request failed: #{error[1]}"

sputnik.on "place_order_fail", (error) ->
    alert "order placement failed: #{error[1]}"

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
    $('#low_margin').text margin[0].toFixed(sputnik.getQuantityPrecision('BTC'))
    $('#high_margin').text margin[1].toFixed(sputnik.getQuantityPrecision('BTC'))

sputnik.on "close", (message) ->
    alert "Connection closed: #{message}"



d3 = window.d3

DataSrc = window.DataSrc = ->
    self = this
    @data = [
    ]
    return

DataSrc::add = (ohlcv) ->
    @last_open_time = new Date(ohlcv.wire_timestamp / 1000)
    ohlcv.open_time = @last_open_time.toISOString()
    @data.push ohlcv
    return

DataSrc::load_history = (ohlcv_history) ->
    @data = []
    for timestamp, ohlcv of ohlcv_history
        @add ohlcv

DataSrc::hasData = () ->
    if @data.length > 0
        return true
    else
        return false

window.dataSrc = new DataSrc()

CandlestickChart = window.CandlestickChart
OHLCChart = window.OHLCChart
VolumeChart = window.VolumeChart
clearCharts = ->
    clearInterval(window.i)
    $("svg").remove()
    $('#lineChart:visible').slideUp(500)
    $('#ohlcChart:visible').slideUp(500)


candlesticksChart = ->
    $('#ohlcChart:hidden').slideDown(500)
    candleCanvas = d3.select("#ohlcChart").append("svg")
    $("br.clear").remove()
    d3.select("#ohlcChart").append("br").attr "class", "clear"
    volumeCanvas = d3.select("#ohlcChart").append("svg")
    myCandlestickChart = candleCanvas.chart("CandlestickChart",
        exchange: window.contract
        period: 60
        width: $('#ohlcChart').width() - 100
    )
    myVolumeChart = volumeCanvas.chart("VolumeChart",
        period: 60
        width: $('#ohlcChart').width() - 100
    )
    if dataSrc.hasData()
        myCandlestickChart.draw dataSrc
        myVolumeChart.draw dataSrc

ohlcChart = ->
    $('#ohlcChart:hidden').slideDown()
    candleCanvas = d3.select("#ohlcChart").append("svg")
    $("br.clear").remove()
    d3.select("#ohlcChart").append("br").attr "class", "clear"
    volumeCanvas = d3.select("#ohlcChart").append("svg")
    myCandlestickChart = candleCanvas.chart("OHLCChart",
        exchange: window.contract
        period: 60
        width: $('#ohlcChart').width() - 100
    )
    myVolumeChart = volumeCanvas.chart("VolumeChart",
        period: 60
        width: $('#ohlcChart').width() - 100
    )
    if dataSrc.hasData()
        myCandlestickChart.draw dataSrc
        myVolumeChart.draw dataSrc

ohlcChartUpdate = (data) ->
    sputnik.log "[chart:598 - ohlcChartUpdate]"
    dataSrc.add(data)

ohlcChartLoad = (history) ->
    dataSrc.load_history(history)

lineChartUpdate = (data) ->
    sputnik.log "[ui:254 - lineChartUpdate]", data
    return if chartMode isnt 'line'
    plot_data = for trade in data
        [trade.wire_timestamp / 1000, trade.price]
    data =
        data: plot_data
        label: 'Trades'

    options =
        xaxis:
            mode: 'time'
            timezone: 'browser'
            format: '%H:%M:%S'
    sputnik.log "[chart:611 - plotting]"
    $.plot("#lineChart", [data], options)

lineChart = ->
    $('#lineChart:hidden').slideDown(500)

chartMode = 'line'
$ ->
    $('.chartNav li').click (e)->
        $('.chartNav .selected').removeClass 'selected'
        clearCharts()
        setTimeout =>
            chartMode = @.className
            switch chartMode
                when "line" then lineChart()
                when "ohlc" then ohlcChart()
                when "candlesticks" then candlesticksChart()
            $(@).addClass('selected')
        ,
        700
        no #don't follow the link to the empty hashtag
lineChart()
