location = window.location
hostname = location.hostname
protocol = location.protocol
if protocol == 'http:'
    ws_protocol = "ws:"
else
    ws_protocol = "wss:"

uri = ws_protocol + "//" + hostname + ":8000"

sputnik = new window.Sputnik uri
window.sputnik = sputnik

sputnik.on "log", (args...) -> ab.log args...
sputnik.on "warn", (args...) -> ab.warn args...
sputnik.on "error", (args...) -> ab.error args...

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
    $("#account_menu").toggle()
    $("#buy_panel").toggle()
    $("#sell_panel").toggle()
    $("#orders_panel").toggle()
    sputnik.getCookie()

sputnik.on "cookie", (uid) ->
    sputnik.log "cookie: " + uid
    document.cookie = "login" + "=" + sputnik?.username + ":" + uid

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

$("#account").click (event) ->
    $("#account_modal").modal()

$("#change_password_button").click (event) ->
    if new_password.value != new_password_confirm.value
        alert "Passwords do not match"
    else
        sputnik.changePassword(old_password.value, new_password.value)

$("#change_profile_button").click (event) ->
    sputnik.changeProfile(new_nickname.value, new_email.value)

$('#deposit_mxn').click (event) ->
    $('#compropago_modal').modal('show')

$('#deposit_btc').click (event) ->
    sputnik.getAddress('BTC')
    $('#deposit_btc_modal').modal('show')

$('#new_address_button').click (event) ->
    sputnik.newAddress('BTC')

$("#compropago_pay_button").click (event) ->
    event.preventDefault()
    ladda = Ladda.create $("#compropago_pay_button")[0]
    ladda.start()
    store = $("#compropago_store").val()
    amount = $("#compropago_amount").val()
    send_sms = $("#compropago_send_sms").is(":checked")
    sputnik.makeCompropagoDeposit store, Number(amount), send_sms

$('#chatButton').click ->
    chat_return = sputnik.chat chatBox.value
    if not chat_return[0]
        alert chat_return[1]

    $('#chatBox').val('')

updateTable = (id, data) ->
    rows = for [price, quantity] in data
        "<tr><td>#{price}</td><td>#{quantity}</td></tr>"
    $("##{id}").html rows.join("")

updateBuys = (data) ->
    data.sort (a, b) ->
        b[0] - a[0]
    updateTable "buys", data
    best_bid = Math.max 0, (price for [price, quantity] in data)...
    if not $("#sell_price").is(":focus") and not $("#sell_quantity").is(":focus")
      $("#sell_price").val best_bid

updateSells = (data) ->
    data.sort (a, b) ->
        a[0] - b[0]
    updateTable "sells", data
    best_ask = Math.min (price for [price, quantity] in data)...
    if not $("#buy_price").is(":focus") and not $("#buy_quantity").is(":focus")
      $("#buy_price").val best_ask

updateTrades = (data) ->
    trades_reversed = data.reverse()
    rows = for trade in trades_reversed[0..20]
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
        button = "<td><button type='button' class='btn btn-danger' onclick='sputnik.cancelOrder(#{id})'>"
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
    sputnik.getOHLCV "BTC/MXN"
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

sputnik.on "chat", (chat_messages) ->
    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "compropago_deposit_success", (message) ->
    alert message

sputnik.on "compropago_deposit_fail", (error) ->
    alert error

sputnik.on "address", (info) ->
    # We only support BTC here
    address = info[1]
    $('#btc_deposit_address').attr('href', 'bitcoin:' + address).text(address)
    $('#btc_deposit_qrcode').empty()
    $('#btc_deposit_qrcode').qrcode("bitcoin:" + address)

sputnik.on "ohlcv", (ohlcv) ->
    for timestamp, entry of ohlcv
        $('#low').text entry.low.toFixed(0)
        $('#high').text entry.high.toFixed(0)
        $('#vwap').text entry.vwap.toFixed(0)

sputnik.on "password_change_success", (info) ->
    alert "Password successfully changed"

sputnik.on "password_change_fail", (error) ->
    alert "Password change fail: #{error}"
