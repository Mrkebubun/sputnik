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
    sputnik.getCookie()

sputnik.on "cookie", (uid) ->
    sputnik.log "cookie: " + uid
    document.cookie = "login" + "=" + login.value + ":" + uid

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

$("#buyButton").click ->
    sputnik.placeOrder(Number(buy_quantity.value), Number(buy_price.value), 'BTC/MXN', 'BUY')

$("#sellButton").click ->
    sputnik.placeOrder(Number(sell_quantity.value), Number(sell_price.value), 'BTC/MXN', 'SELL')

$("#logout").click (event) ->
    document.cookie = ''
    sputnik.logout()
    location.reload()

updateTable = (id, data) ->
    rows = for [price, quantity] in data
        "<tr><td>#{price}</td><td>#{quantity}</td></tr>"
    $("##{id}").html rows.join("")

updateBuys = (data) ->
    data.sort (a, b) ->
        b[0] - a[0]
    updateTable "buys", data
    best_offer = Math.max 0, (price for [price, quantity] in data)...
    $("#sell_price").attr "placeholder", best_offer

updateSells = (data) ->
    data.sort (a, b) ->
        a[0] - b[0]
    updateTable "sells", data
    best_offer = Math.min (price for [price, quantity] in data)...
    $("#buy_price").attr "placeholder", best_offer

updateTrades = (data) ->
    rows = for trade in data.reverse()
        "<tr><td>#{trade.price}</td><td>#{trade.quantity}</td><td>#{trade.timestamp}</td></tr>"
    $("#trades").html rows.join("")

updatePlot = (data) ->
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

    $.plot("#graph", [data], options)

updateOrders = (orders) ->
    rows = []
    for id, order of orders
        icon = "<span class='label label-warning'>Sell</span>"
        if order.side is "BUY"
            icon = "<span class='label label-primary'>Buy</span>"
        icon = "<td>#{icon}</td>"
        price = "<td>#{order.price}</td>"
        quantity = "<td>#{order.quantity_left}</td>"
        #timestamp = "<td>#{order.timestamp}</td>"
        #id = "<td>#{id}</td>"
        button = "<td><button type='button' class='btn btn-danger' onclick='cancelOrder(#{id})'>"
        button += "<span class='glyphicon glyphicon-trash'></span>"
        button += "</button></td>"
        rows.push "<tr>" + icon + price + quantity + button + "</tr>"

    $("#orders").html rows.join("")

$ ->
    sputnik.connect()

sputnik.on "trade_history", (trade_history) ->
    updateTrades(trade_history['BTC/MXN'])
    updatePlot(trade_history['BTC/MXN'])

sputnik.on "open", () ->
    sputnik.log "open"
    sputnik.getOrderBook "BTC/MXN"
    sputnik.getTradeHistory "BTC/MXN"
    sputnik.follow "BTC/MXN"

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
    updateBuys ([book_row.price, book_row.quantity] for book_row in book["BTC/MXN"].bids)
    updateSells ([book_row.price, book_row.quantity] for book_row in book["BTC/MXN"].asks)

sputnik.on "orders", (orders) ->
    updateOrders orders

sputnik.on "trade", (trade) ->
    if trade.contract == "BTC/MXN"
        $('#last').text trade.price.toFixed(0)

sputnik.on "positions", (positions) ->
    MXNpos = positions['MXN'].position
    BTCpos = positions['BTC'].position
    $('#MXNpos').text MXNpos.toFixed(0)
    $('#BTCpos').text BTCpos.toFixed(2)