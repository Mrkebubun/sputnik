class @Locale

    constructor: (@locale_str, @sputnik) ->
        @supported_locales =
            en: {}
            pt: {}
            es: {}
            "pt-BR": {}
            "es-419": {}

        @country_to_locale =
            BR: "pt"
            HN: "es"
            US: "en"
            CO: "es"
            AR: "es"

    init: () =>
        this_object = this
        $.get( "locale/translations.json", (data) =>
            Globalize.loadTranslations(data)
        ).then( () ->
            $.when(
                $.get( "cldr/supplemental/likelySubtags.json" ),
                $.get( "cldr/supplemental/timeData.json" ),
                $.get( "cldr/supplemental/weekData.json" ),
                $.get( "cldr/supplemental/plurals.json" ),
            ).then( () ->
                [].slice.apply(arguments, [0]).map (result) ->
                    result[0]
            ).then(Globalize.load).then( () ->
                $.when(
                    # TODO: Use the supported_locales to do all these calls
                    this_object.loadLocale("en"),
                    this_object.loadLocale("pt"),
                    this_object.loadLocale("pt-BR"),
                    this_object.loadLocale("es"),
                    this_object.loadLocale("es-419")
                )
            )
        ).then( () ->
            for locale_str, details of this_object.supported_locales
                details.gl = new Globalize(locale_str)
        )

    loadLocale: (locale_str) =>
        $.when(
            $.get( "cldr/main/#{locale_str}/ca-gregorian.json" ),
            $.get( "cldr/main/#{locale_str}/timeZoneNames.json" ),
            $.get( "cldr/main/#{locale_str}/numbers.json"),
        ).then( () =>
            [].slice.apply(arguments, [0]).map (result) ->
                result[0]
        ).then(Globalize.load)

    # Make sure that we support this locale before we try to use it
    checkLocale: (locale_str) =>
        if @supported_locales[locale_str]?.gl?
            return locale_str
        else
            return "en"

    translate: (path, locale_str) =>
        translated = @supported_locales[@checkLocale(locale_str)].gl.translate(path)
        if not translated?
            @sputnik.error "Unable to translate: #{path} in #{@checkLocale(locale_str)}"
            return path
        else
            return translated

    priceFormat: (ticker, price, locale_str) =>
        precision = @sputnik.getPricePrecision(ticker)
        fn = @supported_locales[@checkLocale(locale_str)].gl.numberFormatter
            useGrouping: true
            minimumFractionDigits: precision
            maximumFractionDigits: precision
        fn(Number(price))

    quantityFormat: (ticker, quantity, locale_str) =>
        precision = @sputnik.getQuantityPrecision(ticker)
        fn = @supported_locales[@checkLocale(locale_str)].gl.numberFormatter
            useGrouping: true
            minimumFractionDigits: precision
            maximumFractionDigits: precision

        fn(Number(quantity))

    timeFormat: (timestamp, locale_str) =>
        fn = @supported_locales[@checkLocale(locale_str)].gl.dateFormatter
            time: "short"
        dt = new Date(timestamp / 1000)
        fn(dt)

    dateTimeFormat: (timestamp, locale_str) =>
        fn = @supported_locales[@checkLocale(locale_str)].gl.dateFormatter
            datetime: "short"
        dt = new Date(timestamp / 1000)
        fn(dt)

    dateFormat: (timestamp, locale_str) =>
        fn = @supported_locales[@checkLocale(locale_str)].gl.dateFormatter
            date: "short"
        dt = new Date(timestamp / 1000)
        fn(dt)

    parseNumber: (string, locale_str) =>
        # Force a string
        # add a leading zero because ",4" doesn't give us 0.4, but "0,4" does
        @supported_locales[@checkLocale(locale_str)].gl.parseNumber("0" + string.toString())

    parseDate: (string, locale_str) =>
        dt = @supported_locales[@checkLocale(locale_str)].gl.parseDate(string,
            date: "short"
        )
        if dt?
            # Convert to sputnik
            return dt.getTime() * 1000
        else
            return NaN

$ ->
    location = window.location
    hostname = location.hostname
    protocol = location.protocol
    if protocol == 'http:'
        ws_protocol = "ws:"
        port = 8880
    else
        ws_protocol = "wss:"
        port = 8443

    uri = ws_protocol + "//" + hostname + ":#{port}"

    sputnik = new Sputnik uri
    window.sputnik = sputnik
    
    locale = new Locale navigator.language, sputnik
    window.locale = locale

    getQueryKey = (key) ->
        query = window.location.search.substring(1);
        pairs = query.split('&').map (p) -> p.split('=')
        results = pairs.filter (p) -> (decodeURIComponent(p[0]) == key)
        final = results.map (p) -> decodeURIComponent(p[1])
        if final.length
            return final[0]
        else
            return undefined

    loadPartial = (name, url) ->
        $.get( url ).then (data) ->
            Ractive.partials[name] = data

    loadAllPartials = () ->
        partial_urls =
            login_register: 'partials/login_register.html'
            change_password_token: 'partials/change_password_token.html'
        results = []
        for name, url of partial_urls
            results.push loadPartial(name, url)

        $.when( results )

    simple_widget = getQueryKey('widget')
    if simple_widget?
        sputnik.log ["simple_widget", simple_widget]
        template_url = "templates/#{simple_widget}.html"
        widget_contract = getQueryKey('contract')
        sputnik.log ["widget_contract", widget_contract]
    else
        template_url = 'templates/full.html'

    locale.init().then () ->
        loadAllPartials().then () ->
            $.ajax {
                url: template_url
                success: (data, status, xhr) ->
                   start(data)
                }

    start = (template) ->
        ractive = new Ractive
            el: "target"
            template: template
            data:
                sputnik: sputnik
                connected: false
                current_ticker: null
                current_type: null
                current_currency: null
                current_page: "dashboard"
                dashboard_tab: "active-contracts"
                account_tab: "profile"
                fh_tab: "deposit"
                tb_tab: "trades"
                audit_tab: "Liability"
                audit_contract: "BTC"
                all_orders_sort_column: "timestamp"
                locale: locale

                format_time: (datetime, locale_str) ->
                    if datetime?
                        locale.timeFormat(datetime, locale_str)

                format_date: (datetime, locale_str) ->
                    if datetime?
                        locale.dateFormat(datetime, locale_str)

                format_datetime: (datetime, locale_str) ->
                    if datetime?
                        locale.dateTimeFormat(datetime, locale_str)

                format_price: (ticker, price, locale_str) ->
                    if price?
                        locale.priceFormat(ticker, price, locale_str)

                format_quantity: (ticker, quantity, locale_str) ->
                    if quantity?
                        locale.quantityFormat(ticker, quantity, locale_str)

                parse_number: (string, locale_str) ->
                    locale.parseNumber(string, locale_str)

                translate: (path, locale_str) ->
                    locale.translate path, locale_str

                price_for_quantity: (ticker, quantity_str, side, locale_str, book) ->
                    price = sputnik.priceForQuantity(ticker, locale.parseNumber(quantity_str, locale_str), side)
                    sputnik.log ["priceforQuantity", ticker, quantity_str, price]
                    locale.priceFormat(ticker, price, locale_str)

                clean_ticker: (ticker) ->
                    ticker.replace('/', '_')
                values: (obj) -> (value for key, value of obj)
                sort: (array, column) ->
                    array = array.slice()
                    array.sort (a, b) -> a[column] < b[column] ? -1 : 1
            transitions:
                show_chart: (t, ticker) ->
                    showChart(ticker, t.node.id, transition=t)
                show_feed: (t) ->
                    showFeed(t)
                show_qr: (t, address) ->
                    $('#qr_code').empty()
                    $('#qr_code').qrcode("bitcoin:" + address)
                    t.complete()

            adapt: [Ractive.adaptors.Sputnik]
            debug: true

        ractive.on
            switch_type: (event, type) ->
                event.original.preventDefault()
                ractive.set "current_type", type

            switch_contract: (event) ->
                event.original.preventDefault()
                ractive.set "current_ticker", event.context

            switch_currency: (event, currency) ->
                event.original.preventDefault()
                ractive.set "current_currency", currency
                sputnik.getAddress(currency)
                sputnik.getDepositInstructions(currency)

            switch_page: (event, page) ->
                event.original.preventDefault()
                ractive.set "current_page", page
                if page is "trade" and ractive.get("current_ticker") is null
                    markets = ractive.get("sputnik.markets")
                    tickers = Object.keys(markets)
                    if tickers.length
                        ractive.set("current_ticker", tickers[0])
                        ractive.set("current_type", markets[tickers[0]].contract_type)
                if page is "account" and ractive.get("sputnik.logged_in") is false
                    $('#login_modal').modal()

            switch_dashboard_tab: (event, tab) ->
                event.original.preventDefault()
                ractive.set "dashboard_tab", tab

            switch_account_tab: (event, tab) ->
                event.original.preventDefault()
                ractive.set "account_tab", tab
                if tab == "audit"
                    sputnik.getAudit()

            switch_fh_tab: (event, tab) ->
                event.original.preventDefault()
                ractive.set "fh_tab", tab

            switch_tb_tab: (event, tab) ->
                event.original.preventDefault()
                ractive.set "tb_tab", tab

            switch_audit_tab: (event, tab) ->
                event.original.preventDefault()
                ractive.set "audit_tab", tab

            switch_audit_contract: (event, ticker) ->
                event.original.preventDefault()
                ractive.set "audit_contract", ticker

            switch_history_contract: (event, ticker) ->
                event.original.preventDefault()
                ractive.set "history_contract", ticker

            withdraw: (event, type) ->
                event.original.preventDefault()
                ticker = ractive.get("current_currency")
                amount = locale.parseNumber($('#withdraw-amount').val(), ractive.get("sputnik.profile.locale"))
                if type == "crypto"
                    address = $('#crypto_address').val()
                    confirm_address = $('#crypto_confirm_address').val()
                    if address != confirm_address
                        bootbox.alert locale.translate("account/funding_history/withdrawal/alerts/mismatched_address", ractive.get("sputnik.profile.locale"))
                        return
                else if type == "wire"
                    address_obj =
                        bank_name: $('#withdraw-bank-name').val()
                        bank_address: $('#withdraw-bank-address').val()
                        aba_swift: $('#withdraw-aba-swift').val()
                        account_name: $('#withdraw-account-name').val()
                        account_number: $('#withdraw-account-number').val()
                    address = JSON.stringify(address_obj)
                else
                    address_obj =
                        name: $('#withdraw-name').val()
                        address1: $('#withdraw-address1').val()
                        address2: $('#withdraw-address2').val()
                        city: $('#withdraw-city').val()
                        state_province: $('#withdraw-state').val()
                        postalcode: $('#withdraw-postalcode').val()
                        country: $('#withdraw-country').val()
                    address = JSON.stringify(address_obj)

                sputnik.requestWithdrawal(ticker, amount, address)

            buykey: (event) ->
                buy_price_str = ractive.get("buy_price")
                buy_quantity_str = ractive.get("buy_quantity")

                if not buy_quantity_str
                    buy_quantity = 0
                buy_quantity = locale.parseNumber(buy_quantity_str, ractive.get("sputnik.profile.locale"))

                if not buy_price_str? or not buy_price_str
                    buy_price = sputnik.priceForQuantity(ractive.get("current_ticker"), buy_quantity, 'BUY')
                else
                    buy_price = locale.parseNumber(buy_price_str, ractive.get("sputnik.profile.locale"))

                alerts = []


                if isNaN(buy_price) or not sputnik.checkPriceValidity(ractive.get("current_ticker"), buy_price)
                    alerts.push locale.translate("trade/alerts/price_invalid", ractive.get("sputnik.profile.locale"))

                if isNaN(buy_quantity) or not sputnik.checkQuantityValidity(ractive.get("current_ticker"), buy_quantity)
                    if buy_quantity_str != ""
                        alerts.push locale.translate("trade/alerts/quantity_invalid", ractive.get("sputnik.profile.locale"))

                if alerts.length == 0
                    if sputnik.authenticated
                        if not sputnik.canPlaceOrder(buy_quantity, buy_price, ractive.get("current_ticker"), 'BUY')
                            alerts.push locale.translate("trade/alerts/insufficient_funds", ractive.get("sputnik.profile.locale"))

                if alerts.length
                    $('#buy_alert').text alerts.join(', ')
                    $('#buy_alert').show()
                    $('#buyButton').hide()
                else
                    $('#buy_alert').hide()
                    $('#buyButton').show()


            sellkey: (event) ->
                sell_price_str = ractive.get("sell_price")
                sell_quantity_str = ractive.get("sell_quantity")

                if not sell_quantity_str == ''
                    sell_quantity = 0
                sell_quantity = locale.parseNumber(sell_quantity_str, ractive.get("sputnik.profile.locale"))

                if not sell_price_str? or not sell_price_str
                    sell_price = sputnik.priceForQuantity(ractive.get("current_ticker"), sell_quantity, 'SELL')
                else
                    sell_price = locale.parseNumber(sell_price_str, ractive.get("sputnik.profile.locale"))

                alerts = []
                if isNaN(sell_price) or not sputnik.checkPriceValidity(ractive.get("current_ticker"), sell_price)
                    alerts.push locale.translate("trade/alerts/price_invalid", ractive.get("sputnik.profile.locale"))

                if isNaN(sell_quantity) or not sputnik.checkQuantityValidity(ractive.get("current_ticker"), sell_quantity)
                    if sell_quantity_str != ""
                        alerts.push locale.translate("trade/alerts/quantity_invalid", ractive.get("sputnik.profile.locale"))

                if alerts.length == 0
                    if sputnik.authenticated
                        if not sputnik.canPlaceOrder(sell_quantity, sell_price, ractive.get("current_ticker"), 'SELL')
                            alerts.push locale.translate("trade/alerts/insufficient_funds", ractive.get("sputnik.profile.locale"))

                if alerts.length
                    $('#sell_alert').text alerts.join(', ')
                    $('#sell_alert').show()
                    $('#sellButton').hide()
                else
                    $('#sell_alert').hide()
                    $('#sellButton').show()


            buy: (event) ->
                event.original.preventDefault()
                buy_quantity = locale.parseNumber(ractive.get("buy_quantity"), ractive.get("sputnik.profile.locale"))
                buy_price_str = ractive.get("buy_price")

                if buy_quantity <= 0 or isNaN(buy_quantity)
                    bootbox.alert locale.translate("trade/alerts/quantity_invalid", ractive.get("sputnik.profile.locale"))
                    return true

                if not buy_price_str? or buy_price_str == ''
                    buy_price = sputnik.priceForQuantity(ractive.get("current_ticker"), buy_quantity, 'BUY')
                    bootbox.confirm(locale.translate("trade/alerts/placing_order_with_price",
                                                     ractive.get("sputnik.profile.locale")) + " " +
                                    locale.priceFormat( ractive.get("current_ticker"), buy_price, ractive.get("sputnik.profile.locale")) + ". " +
                                    locale.translate("trade/alerts/are_you_sure", ractive.get("sputnik.profile.locale")), (result) =>
                        if result
                            sputnik.placeOrder(buy_quantity, buy_price, ractive.get("current_ticker"), 'BUY')
                    )
                else
                    buy_price = locale.parseNumber(buy_price_str, ractive.get("sputnik.profile.locale"))
                    if buy_price <= 0 or isNaN(buy_price)
                        bootbox.alert locale.translate("trade/alerts/price_invalid", ractive.get("sputnik.profile.locale"))
                        return true

                    if not withinAnOrderOfMagnitude(buy_price, ractive.get("sputnik.books")[ractive.get("current_ticker")].best_ask.price)
                        bootbox.confirm locale.translate("trade/alerts/strange_price", ractive.get("sputnik.profile.locale")), (result) ->
                            if result
                                sputnik.placeOrder(buy_quantity, buy_price, ractive.get("current_ticker"), 'BUY')
                    else
                        sputnik.placeOrder(buy_quantity, buy_price, ractive.get("current_ticker"), 'BUY')

            sell: (event) ->
                event.original.preventDefault()
                sell_quantity = locale.parseNumber(ractive.get("sell_quantity"), ractive.get("sputnik.profile.locale"))
                sell_price_str = ractive.get("sell_price")


                if sell_quantity <= 0 or isNaN(sell_quantity)
                    bootbox.alert locale.translate("trade/alerts/quantity_invalid", ractive.get("sputnik.profile.locale"))
                    return true

                if not sell_price_str? or sell_price_str == ''
                    sell_price = sputnik.priceForQuantity(ractive.get("current_ticker"), sell_quantity, 'SELL')
                    bootbox.confirm(locale.translate("trade/alerts/placing_order_with_price",
                                                     ractive.get("sputnik.profile.locale")) + " " +
                                    locale.priceFormat( ractive.get("current_ticker"), sell_price, ractive.get("sputnik.profile.locale")) + ". " +
                                    locale.translate("trade/alerts/are_you_sure", ractive.get("sputnik.profile.locale")), (result) =>
                        if result
                            sputnik.placeOrder(sell_quantity, sell_price, ractive.get("current_ticker"), 'SELL')
                    )
                else
                    sell_price = locale.parseNumber(sell_price_str, ractive.get("sputnik.profile.locale"))
                    if sell_price <= 0 or isNaN(sell_price)
                        bootbox.alert locale.translate("trade/alerts/price_invalid", ractive.get("sputnik.profile.locale"))

                    if not withinAnOrderOfMagnitude(sell_price, ractive.get("sputnik.books")[ractive.get("current_ticker")].best_bid.price)
                        bootbox.confirm locale.translate("trade/alerts/strange_price", ractive.get("sputnik.profile.locale")), (result) ->
                            if result
                                sputnik.placeOrder(sell_quantity, sell_price, ractive.get("current_ticker"), 'SELL')
                    else
                        sputnik.placeOrder(sell_quantity, sell_price, ractive.get("current_ticker"), 'SELL')

            transactions: (event) ->
                event.original.preventDefault()
                sputnik.log ["get_history", $("#transactions_start_date").val(), $("#transactions_end_date").val()]
                start_timestamp = locale.parseDate($("#transactions_start_date").val(), ractive.get("sputnik.profile.locale"))
                end_timestamp = locale.parseDate($("#transactions_end_date").val(), ractive.get("sputnik.profile.locale"))
                now = new Date()
                if isNaN(start_timestamp)
                    start = new Date()
                    start.setDate(now.getDate() - 7)
                    start_timestamp = start.getTime() * 1000
                    $('#transactions_start_date').val(locale.dateFormat(start_timestamp, ractive.get("sputnik.profile.locale")))
                    $("#transactions_start_date").fadeIn(100).fadeOut(100).fadeIn(100).fadeOut(100).fadeIn(100);

                if isNaN(end_timestamp)
                    end = new Date()
                    end.setDate(now.getDate())
                    # Add a day because we want the end of the day not the beginning
                    end_timestamp = end.getTime() * 1000 + 3600 * 24 * 1000000
                    $('#transactions_end_date').val(locale.dateFormat(end_timestamp - 3600 * 24 * 1000000, ractive.get("sputnik.profile.locale")))
                    $("#transactions_end_date").fadeIn(100).fadeOut(100).fadeIn(100).fadeOut(100).fadeIn(100);
                else
                    # Add a day because we want the end of the day not the beginning
                    end_timestamp += 3600 * 24 * 1000000

                if end_timestamp <= start_timestamp
                    # One day of data
                    end_timestamp = start_timestamp + 3600 * 24 * 1000000
                    $('#transactions_end_date').val(locale.dateFormat(start_timestamp, ractive.get("sputnik.profile.locale")))
                    $("#transactions_end_date").fadeIn(100).fadeOut(100).fadeIn(100).fadeOut(100).fadeIn(100);

                sputnik.getTransactionHistory(start_timestamp, end_timestamp)

            submit_compliance: (event) ->
                event.original.preventDefault()
                compliance_client_handler($('#compliance form').eq(0))

            change_profile: (event) ->
                event.original.preventDefault()
                sputnik.changeProfile(ractive.get("sputnik.profile"))

            change_password: (event) ->
                event.original.preventDefault()
                if $('#new_password').val() isnt $('#new_password_confirm').val()
                    bootbox.alert locale.translate("alerts/mismatched_password", ractive.get("sputnik.profile.locale"))
                else
                    sputnik.changePassword $('#old_password').val(), $('#new_password_confirm').val()

            change_password_token: (event) ->
                event.original.preventDefault()
                if $('#new_password_token').val() == $('#new_password_token_confirm').val()
                    sputnik.changePasswordToken($('#new_password_token').val())
                else
                    $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-danger').text locale.translate("alerts/mismatched_password", ractive.get("sputnik.profile.locale"))

            show_login_register: (event) ->
                event.original.preventDefault()
                $('#login_modal').modal()
                $("#login_modal").on 'hidden.bs.modal', ->
                    $('#register_error').hide()
                    $('#login_error').hide()
                    $('#reset_token_sent').hide()

            login: (event) ->
                event.original.preventDefault()

                username = $("#login_username").val()
                password = $("#login_password").val()

                if username is ''
                    $("#login_error").text(locale.translate("alerts/invalid_username", ractive.get("sputnik.profile.locale"))).show()
                else
                    $("#login_error").hide()
                    ladda = Ladda.create $("#login_button")[0]
                    ladda.start()
                    sputnik.authenticate username, password
                    $('#login_modal .alert:visible').hide()

            register: (event) ->
                event.original.preventDefault()

                username = $("#register_email").val()
                password = $("#register_password").val()
                email = $("#register_email").val()
                nickname = $("#register_email").val()
                eula = $("#register_eula").is(":checked")

                re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
                if not re.test(email)
                    $('#register_error').text(locale.translate("alerts/invalid_email", ractive.get("sputnik.profile.locale"))).slideDown()
                else
                    if username and password and email and nickname and eula
                        $('#register_error').hide()
                        ladda = Ladda.create $("#register_button")[0]
                        ladda.start()
                        sputnik.makeAccount username, password, email, nickname, ractive.get("sputnik.profile.locale")
                    else
                        $('#register_error').text(locale.translate("alerts/complete_registration", ractive.get("sputnik.profile.locale"))).slideDown()

            get_reset_token: (event) ->
                event.original.preventDefault()
                username = $("#login_username").val()
                $('#login_modal .alert:visible').hide()

                if not username.length
                    $('#login_error').text(locale.translate("alerts/enter_username", ractive.get("sputnik.profile.locale"))).slideDown()
                    return

                sputnik.getResetToken(username)
                $('#reset_token_sent').show()
                setTimeout(
                    ->
                        $('#login_modal .alert:visible').hide()
                        $("#login_modal").modal "hide"
                ,
                5000)
                ga('send', 'event', 'password', 'get_reset_token')

            logout: (event) ->
                event.original.preventDefault()
                document.cookie = ''
                sputnik.logout()
                location.reload()

            cancel_order: (event, id) ->
                event.original.preventDefault()
                sputnik.cancelOrder(parseInt(id))

            new_address: (event, ticker) ->
                event.original.preventDefault()
                sputnik.newAddress(ticker)

            sort_all_orders: (event, column) ->
                ractive.set("all_orders_sort_column", column)


        ractive.observe "current_ticker", (new_ticker, old_ticker, path) ->
            if old_ticker?
                sputnik.unfollow old_ticker
            if new_ticker?
                ractive.set "buy_price", ""
                ractive.set "buy_quantity", ""
                ractive.set "sell_price", ""
                ractive.set "sell_quantity", ""
                # TODO: change this to a template {{if}}
                $("#buy_alert").hide()
                $("#buyButton").show()
                $("#sell_alert").hide()
                $("#sellButton").show()

                if not simple_widget?
                    sputnik.openMarket new_ticker
                    showChart new_ticker

        window.ractive = ractive

        setWindowInfo = () ->
            window_info =
                width: $(window).width()
                height: $(window).height()
            ractive.set "window_info", window_info

        setWindowInfo()
        $(window).resize setWindowInfo

        # Get location. Try geoip first,
        # Then try geolocation
        geoip2.country (result) ->
            sputnik.log ["geoip", result]
            if not sputnik.authenticated
                country = result.country.iso_code
                if locale.country_to_locale[country]?
                    ractive.set("sputnik.profile.locale", locale.country_to_locale[country])
        , (error) ->
            sputnik.error ["geoip error", error]
            if navigator.geolocation
                navigator.geolocation.getCurrentPosition (position) ->
                    sputnik.log ["current_position", position]
                    lat = position.coords.latitude
                    lng = position.coords.longitude
                    latlng = new google.maps.LatLng(lat, lng);
                    # For debugging
                    # Rio de Janerio, Brazil
                    #latlng = new google.maps.LatLng(-22.9027800, -43.2075000)
                    # San Pedro Sula, Honduras
                    #latlng = new google.maps.LatLng(15.503659,-88.00468)
                    # Berlin, Germany
                    #latlng = new google.maps.LatLng(52.5243700, 13.4105300)
                    geocoder = new google.maps.Geocoder();
                    geocoder.geocode {'latLng': latlng}, (results, status) ->
                        # If we're already logged in by now, don't set the locale
                        if not sputnik.authenticated
                            if status == google.maps.GeocoderStatus.OK
                                sputnik.log ["reverse geocode", results]
                                # Find the result with types country and political
                                useful_results = results.filter (r) -> "political" in r.types and "country" in r.types
                                components = useful_results.map (r) -> r.address_components
                                useful_components = components.map (c) -> c.filter (r) -> "political" in r.types and "country" in r.types
                                short_names = useful_components.map (c) -> c.map (r) -> r.short_name
                                short_names_flat = short_names.reduce (l,r)->l.concat(r)
                                sputnik.log ["short_names", short_names_flat]

                                for country in short_names
                                    if locale.country_to_locale[country]?
                                        ractive.set("sputnik.profile.locale", locale.country_to_locale[country])

        tv = new window.TVFeed sputnik
        window.tv = tv

        sputnik.on "log", (args...) -> ab.log args...
        sputnik.on "warn", (args...) -> ab.log args...
        sputnik.on "error", (args...) -> ab.log args...

        sputnik.on "open", () ->
            sputnik.log "open"
            ractive.set("connected", true)

            # Attempt a cookie login
            full_cookie = document.cookie
            sputnik.log "full_cookie: #{full_cookie}"
            if full_cookie
                cookies = full_cookie.split(';')
                for cookie in cookies
                    field_value = cookie.trim().split("=", 2)
                    if field_value[0] == "login"
                        name_uid = field_value[1].split(":", 2)

                        if !name_uid[1]
                            sputnik.log "resetting cookie to null"
                            document.cookie = ''
                        else
                            sputnik.log "attempting cookie login with: #{name_uid[1]}"
                            sputnik.restoreSession name_uid[1]

            if simple_widget?
                if simple_widget == "trade"
                    ractive.set "current_ticker", widget_contract
                    sputnik.openMarket widget_contract

            if simple_widget == "funding"
                ractive.set "current_currency", widget_contract

        sputnik.on "auth_success", (username) ->
            ga('send', 'event', 'login', 'success')
            ladda = Ladda.create $("#login_button")[0]
            ladda.stop()
            $("#login_modal").modal "hide"
            ladda = Ladda.create $("#register_button")[0]
            ladda.stop()
            $("#register_modal").modal "hide"
            sputnik.getCookie()

            if simple_widget == "funding"
                sputnik.getAddress(widget_contract)
                sputnik.getDepositInstructions(widget_contract)

        sputnik.on "cookie", (uid) ->
            sputnik.log "got cookie: " + uid
            document.cookie = "login" + "=" + sputnik?.username + ":" + uid

        sputnik.on "auth_fail", (error) ->
            ga('send', 'event', 'login', 'failure')
            ladda = Ladda.create $("#login_button")[0]
            ladda.stop()
            $("#login_error").text(locale.translate("alerts/bad_username_pw", ractive.get("sputnik.profile.locale"))).show()

        sputnik.on "make_account_success", () ->
            ga('send', 'event', 'register', 'success')
            # do not clear the modal yet, do it in auth_success
            username = $("#register_email").val()
            password = $("#register_password").val()
            sputnik.authenticate username, password

        sputnik.on "make_account_fail", (event) ->
            ga('send', 'event', 'register', 'failure', event[1][0])
            ladda = Ladda.create $("#register_button")[0]
            ladda.stop()
            $("#register_error").text(locale.translate(event[1][0], ractive.get("sputnik.profile.locale")))
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
          $('#compropago_error').text(event[0])
          $('#compropago_error').show()

        withinAnOrderOfMagnitude = (x, y) ->
            sign = (number) -> if number then (if number < 0 then -1 else 1) else 0
            orderOfMag = (w) ->  sign(w) * Math.ceil(Math.log(Math.abs(w) + 1) / Math.log(10))
            orderOfMag(x) == orderOfMag(y)

#        $("#compropago_pay_button").click (event) ->
#            event.preventDefault()
#            ladda = Ladda.create $("#compropago_pay_button")[0]
#            ladda.start()
#            store = $("#compropago_store").val()
#            amount = $("#compropago_amount").val()
#            send_sms = $("#compropago_send_sms").is(":checked")
#            customer_email = $('#compropago_email').val()
#            customer_phone = $('#compropago_phone').val()
#            customer_phone_company = $('#compropago_phone_company').val()
#
#            if (locale.parseNumber(amount, ractive.get("sputnik.profile.locale")) < 6000)
#              sputnik.makeCompropagoDeposit store, locale.parseNumber(amount, ractive.get("sputnik.profile.locale")), customer_email, send_sms, customer_phone, customer_phone_company

#        $('#chatButton').click ->
#            chat_return = sputnik.chat chatBox.value
#            if not chat_return[0]
#                bootbox.alert chat_return[1]
#
#            $('#chatBox').val('')

        showChart = (contract, target="tv_chart_container", transition=null) ->
            sputnik.log ["Show chart", contract, target]
            options =
                fullscreen: false
                symbol: contract
                interval: "60"
                toolbar_bg: '#f4f7f9'
                allow_symbol_change: false
                container_id: target
                datafeed: window.tv
                library_path: "charting_library/"
                locale: "en"
                theme: "White"
                style: "2"
                hideideas: true
                hide_top_toolbar: true
                withdateranges: false
                details: false
                save_image: false
                show_popup_button: false
                disabled_features: ["use_localstorage_for_settings", "header_symbol_search", "header_settings", "header_indicators", "header_compare", "header_undo_redo", "header_screenshot", "header_properties", "left_toolbar"]
                enabled_features: ["narrow_chart_enabled"]
                width: '100%'
                autosize: true
                overrides:
                    "symbolWatermarkProperties.transparency": 100

            if target is "tv_chart_container"
                options.height = 480
                options.autosize = true
            else
                options.height = 240
                options.disabled_features.push "header_widget"
                options.disabled_features.push "control_bar"

            widget = new TradingView.widget options

            widget.onChartReady () ->
                sputnik.log("onChartReady")
                $("##{target} iframe").contents().find(".chart-status-picture").hide()
                if target isnt "tv_chart_container"
                    $("##{target} iframe").contents().find(".onchart-tv-logo").hide()
                    $("##{target} iframe").contents().find(".pane-legend").hide()
                    $("##{target} iframe").contents().find(".chart-controls-bar").hide()

                if transition?
                    transition.complete()

        showFeed = (t) ->
            href = window.location.href
            feed_uri = href.substring(0, href.lastIndexOf('/') + 1) + "feed/"
            $.get feed_uri, (data) ->
                image = $(data).find("image")
                feed =
                    image_url: $(image).find("url").text().replace("http://", "https://")
                    image_title: $(image).find("title").text()
                    image_link: $(image).find("link").text()
                    items: []

                $(data).find("item").each () ->
                    el = $(this)
                    date = new Date(Date.parse(el.find("pubDate").text()))
                    description = el.find("description").text().replace("http://", "https://")
                    item =
                        title: el.find("title").first().text()
                        link: el.find("link").text()
                        date: locale.dateFormat(date.getTime() * 1000, ractive.get("sputnik.profile.locale"))
                        description: description
                    feed.items.push item

                t.root.set "feed", feed

        sputnik.on "change_password_token", (args) ->
            $('#change_password_token_modal').modal "show"

        sputnik.on "exchange_info", (exchange_info) ->
          ga('create', exchange_info.google_analytics, 'auto')
          ga('require', 'linkid', 'linkid.js')
          ga('require', 'displayfeatures')
          ga('send', 'pageview')
          document.title = exchange_info.exchange_name

        sputnik.on "change_password_fail", (error) -> #BUG: this is not firing multiple times
            ga('send', 'event', 'password', 'change_password_fail', 'error', error[1][0])
            bootbox.alert locale.translate(error[1][0], ractive.get("sputnik.profile.locale"))

        sputnik.on "change_password_token_fail", (error) -> #BUG: this is not firing multiple times
            ga('send', 'event', 'password', 'change_password_token_fail', 'error', error[1][0])
            $('#change_password_token_modal').modal "hide"
            window.location.hash = ''
            bootbox.alert locale.translate(error[1][0], ractive.get("sputnik.profile.locale"))

        sputnik.on "change_password_token_success", (message) ->
            ga('send', 'event', 'password', 'change_password_token_success')
            $('#change_password_token_modal').modal "hide"
            window.location.hash = ''
            bootbox.alert locale.translate("alerts/password_reset", ractive.get("sputnik.profile.locale"))

        sputnik.on "change_password_success", (message) ->
            ga('send', 'event', 'password', 'change_password_success')
            bootbox.alert locale.translate("alerts/password_reset", ractive.get("sputnik.profile.locale"))

        sputnik.on "change_profile_success", (profile) ->
            ga('send', 'event', 'profile', 'change_profile_success')
            bootbox.alert locale.translate("alerts/profile_changed", ractive.get("sputnik.profile.locale"))

        sputnik.on "session_expired", ->
            console.log "Session is stale."
            document.cookie = ''

    #    We are disabling chat for now in the UI because we didn't make space for it
    #    sputnik.on "chat_history", (chat_messages) ->
    #        $('#chatArea').html(chat_messages.join("\n"))
    #        $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight)
    #
    #    sputnik.on "chat", (chat) ->
    #        $.growl({title: "Chat", message: chat})

        sputnik.on "address_fail", (error) ->
            ga('send', 'event', 'deposit', 'address_fail', 'error', error[1][0])
            bootbox.alert locale.translate(error[1][0], ractive.get("sputnik.profile.locale"))

        sputnik.on "address", (address) =>
            ga('send', 'event', 'deposit', 'address')
            $('#qr_code').empty()
            if address[0] == "BTC"
                $('#qr_code').qrcode("bitcoin:" + address[1])

        sputnik.on "request_withdrawal_success", (info) ->
            ga('send', 'event', 'withdraw', 'request_withdrawal_success')
            bootbox.alert locale.translate("account/funding_history/withdrawal/alerts/request_placed", ractive.get("sputnik.profile.locale"))

        sputnik.on "request_withdrawal_fail", (error) ->
            ga('send', 'event', 'withdraw', 'request_withdrawal_fail', 'error', error[1][0])
            bootbox.alert locale.translate(error[1][0], ractive.get("sputnik.profile.locale"))

        sputnik.on "place_order_fail", (error) ->
            ga('send', 'event', 'order', 'place_order_fail', 'error', error[1][0])
            bootbox.alert locale.translate(error[1][0], ractive.get("sputnik.profile.locale"))

        sputnik.on "place_order_success", (info) ->
            ga('send', 'event', 'order', 'place_order_success')
            bootbox.alert locale.translate("trade/alerts/place_order_success", ractive.get("sputnik.profile.locale"))

        sputnik.on "fill", (fill) ->
            if not simple_widget?
                fill_notifications = ractive.get("sputnik.profile.notifications.fill")
                if fill_notifications? and "growl" in fill_notifications
                    quantity_fmt = locale.quantityFormat(fill.contract, fill.quantity, ractive.get("sputnik.profile.locale"))
                    price_fmt = locale.priceFormat(fill.contract, fill.price, ractive.get("sputnik.profile.locale"))
                    $.growl.notice { title: locale.translate("trade/titles/fill", ractive.get("sputnik.profile.locale")), message: "#{fill.contract}:#{fill.side}:#{quantity_fmt}@#{price_fmt}" }

        sputnik.on "close", (message) ->
            ga('send', 'event', 'close', 'close')
            ractive.set("connected", false)

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
            ladda = Ladda.create $('#compliance_button')[0]
            ladda.start()
            fd = new FormData()
            fd.append('username', ractive.get("sputnik.username"))
            id_files = form.find('input[name=id_file]')[0].files
            residencies = form.find('input[name=residency]')[0].files

            if not id_files.length
                bootbox.alert locale.translate("account/compliance/alerts/id_required", ractive.get("sputnik.profile.locale"))
                ladda.stop()
                ga('send', 'event', 'compliance', 'failure', 'error', 'id_required')
                return

            if not residencies.length
                bootbox.alert locale.translate("account/compliance/alerts/residency_required", ractive.get("sputnik.profile.locale"))
                ladda.stop()
                ga('send', 'event', 'compliance', 'failure', 'error', 'residency_required')
                return

            fd.append('file', id_files[0])
            fd.append('file', residencies[0])
            fd.append('data', JSON.stringify(form.serializeObject()))

            sputnik.getRequestSupportNonce 'Compliance', (nonce) ->
                fd.append('nonce', nonce)

                $.ajax
                    url: "#{location.origin}/ticket_server/create_kyc_ticket",
                    data: fd,
                    processData: false,
                    contentType: false,
                    type: 'POST',
                    success: (data) ->
                        ladda.stop()
                        ga('send', 'event', 'compliance', 'save', 'number', data.result)
                        bootbox.alert locale.translate("account/compliance/alerts/request_success", ractive.get("sputnik.profile.locale"))
                    error: (error) ->
                        ladda.stop()
                        ga('send', 'event', 'compliance', 'failure', 'error', error.responseJSON[0])
                        bootbox.alert locale.translate(error.responseJSON[0], ractive.get("sputnik.profile.locale"))
                        sputnik.log ["Error:", error]

        # Now that everything is setup, let's connect
        sputnik.connect()

