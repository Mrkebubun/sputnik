sputnik = new window.Sputnik "ws://localhost:8000"

sputnik.on "auth_success", (username) ->
    ladda = Ladda.create $("#login_button")[0]
    ladda.stop()
    $("#login_modal").modal "hide"
    ladda = Ladda.create $("#register_button")[0]
    ladda.stop()
    $("#register_modal").modal "hide"

    $("#login").toggle()
    $("#register").toggle()
    $("#mxn_balance").toggle()
    $("#btc_balance").toggle()
    $("#login_name").text username
    $("#account").toggle()
    $("#buy_panel").toggle()
    $("#sell_panel").toggle()
    $("#orders_panel").toggle()

sputnik.on "auth_fail", ->
    ladda = Ladda.create $("#login_button")[0]
    ladda.stop()
    $("#login_error").show()

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

$("#login").click () ->
    $("#login_modal").modal()

$("#login_button").click (event) ->
    event.preventDefault()
    $("#login_error").hide()
    ladda = Ladda.create $("#login_button")[0]
    ladda.start()
    username = $("#login_username").val()
    password = $("#login_password").val()
    sputnik.authenticate username, password

$("#register").click () ->
    $("#register_modal").modal()

$("#register_button").click (event) ->
    event.preventDefault()
    $("#register_error").hide()
    ladda = Ladda.create $("#register_button")[0]
    ladda.start()
    username = $("#register_username").val()
    password = $("#register_password").val()
    email = $("#register_email").val()
    sputnik.makeAccount username, password, email

$("#logout").click (event) ->
    location.reload()

updateTable = (id, data) ->
    rows = for [price, quantity] in data
        "<tr><td>#{price}</td><td>#{quantity}</td></tr>"
    $("##{id}").html rows.join("")

initPlot = () ->
    d1 = ([i/2, 30*Math.sin(i/2) + 55] for i in [0..28])
    d2 = ([i, 100*Math.sin(i) + 100] for i in [0..13])
    $.plot "#graph",
        [{data:d1, yaxis:1}, {data:d2, bars:{show:true}, yaxis:2}],
        {yaxes:[{position:"left"}, {position:"right"}]}

updateBuys = (data) ->
    data.sort (a, b) -> b[0] - a[0]
    updateTable "buys", data
    best_offer = Math.max 0, (price for [price, quantity] in data)...
    $("#sell_price").attr "placeholder", best_offer

updateSells = (data) ->
    data.sort (a, b) -> a[0] - b[0]
    updateTable "sells", data
    best_offer = Math.min (price for [price, quantity] in data)...
    $("#buy_price").attr "placeholder", best_offer

updateTrades = (data) ->
    updateTable "trades", data

updateOrders = (orders) ->
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

updateTicker = (ticker) ->
    $("#last").text ticker.last
    $("#low").text ticker.low
    $("#high").text ticker.high
    $("#vwap").text ticker.vwap

onLogin = (username) ->

$ ->
    initPlot()
    sample_buys = [[1, 2], [2, 3]]
    sample_sells = [[3, 1], [4, 2]]
    sample_trades = [[2.5, 100]]
    updateBuys sample_buys
    updateSells sample_sells
    updateTrades sample_trades
    sputnik.connect()


