class window.UI
    constructor: (@sputnik) ->
        @sputnik.connect()

        @sputnik.on "auth_success", (username) ->
            login_ladda = Ladda.create $("#login_button")[0]
            login_ladda.stop()
            $("#login_modal").modal "hide"
        
        @sputnik.on "auth_fail", ->
            login_ladda = Ladda.create $("#login_button")[0]
            login_ladda.stop()
            $("#login_error").show()

        $("#login").click () ->
            $("#login_modal").modal()

        $("#login_button").click (event) =>
            event.preventDefault()
            $("#login_error").hide()
            login_ladda = Ladda.create $("#login_button")[0]
            login_ladda.start()
            username = $("#login_username").val()
            password = $("#login_password").val()
            @sputnik.authenticate username, password

        $("#register").click () ->
            $("#register_modal").modal()

    updateTable: (id, data) ->
        rows = for [price, quantity] in data
            "<tr><td>#{price}</td><td>#{quantity}</td></tr>"
        $("##{id}").html rows.join("")

    initPlot: () ->
        d1 = ([i/2, 30*Math.sin(i/2) + 55] for i in [0..28])
        d2 = ([i, 100*Math.sin(i) + 100] for i in [0..13])
        $.plot "#graph",
            [{data:d1, yaxis:1}, {data:d2, bars:{show:true}, yaxis:2}],
            {yaxes:[{position:"left"}, {position:"right"}]}

    updateBuys: (data) ->
        data.sort (a, b) -> b[0] - a[0]
        updateTable "buys", data
        best_offer = Math.max 0, (price for [price, quantity] in data)...
        $("#sell_price").attr "placeholder", best_offer

    updateSells: (data) ->
        data.sort (a, b) -> a[0] - b[0]
        updateTable "sells", data
        best_offer = Math.min (price for [price, quantity] in data)...
        $("#buy_price").attr "placeholder", best_offer

    updateTrades: (data) ->
        updateTable "trades", data

    updateOrders: (orders) ->
        rows = for order in orders
            icon = "<span class='label label-warning'>Sell</span>"
            if order.side is "BUY"
                icon = "<span class='label label-primary'>Buy</span>"
            icon = "<td>#{icon}</td>"
            price = "<td>#{order.price}</td>"
            quantity = "<td>#{order.quantity}</td>"
            button = "<td><button type='button' class='btn btn-danger'>"
            button += "<span class='glyphicon glyphicon-trash'></span>"
            button += "</button></td>"
            "<tr>" + icon + price + quantity + button + "</tr>"
        $("##{orders}").html rows.join("")

    updateTicker: (ticker) ->
        $("#last").text ticker.last
        $("#low").text ticker.low
        $("#high").text ticker.high
        $("#vwap").text ticker.vwap

    onLogin: (username) ->
        $("#register").toggle()
        $("#mxn_balance").toggle()
        $("#btc_balance").toggle()
        $("#buy_panel").toggle()
        $("#sell_panel").toggle()
        $("#orders_panel").toggle()
        $("#login").text "Logged in as #{username}"

    onLogout: ->
        $("#register").toggle()
        $("#mxn_balance").toggle()
        $("#btc_balance").toggle()
        $("#buy_panel").toggle()
        $("#sell_panel").toggle()
        $("#orders_panel").toggle()
        $("#login").text "Login"


$ ->
    sputnik = new window.Sputnik "ws://localhost:8000"
    ui = new window.UI sputnik
    ui.initPlot()
    sample_buys = [[1, 2], [2, 3]]
    sample_sells = [[3, 1], [4, 2]]
    sample_trades = [[2.5, 100]]
    ui.updateBuys sample_buys
    ui.updateSells sample_sells
    ui.updateTrades sample_trades

