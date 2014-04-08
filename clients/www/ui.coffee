location = window.location
hostname = location.hostname
protocol = location.protocol
if protocol == 'http:'
    ws_protocol = "ws:"
else
    ws_protocol = "wss:"

uri = ws_protocol + "//" + hostname + ":8000"

window.best_ask = {price: 0, quantity: 0}
window.best_bid = {price: 0, quantity: 0}

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
    $("#mxn_balance").toggle()
    $("#btc_balance").toggle()
    $("#login_name").text username
    $("#acct_management_username").val username
    $("#account_menu").toggle()
    $("#buy_panel").toggle()
    $("#sell_panel").toggle()
    $("#orders_panel").toggle()
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
    $("#register_modal").modal()

$("#register_button").click (event) ->
    event.preventDefault()
    $("#register_error").hide()
    ladda = Ladda.create $("#register_button")[0]
    ladda.start()
    username = $("#register_username").val()
    password = $("#register_password").val()
    email = $("#register_email").val()
    nickname = $("#register_nickname").val()
    sputnik.makeAccount username, password, email, nickname

withinAnOrderOfMagnitude = (x, y) ->
    sign = (number) -> if number then (if number < 0 then -1 else 1) else 0
    orderOfMag = (w) ->  sign(w) * Math.ceil(Math.log(Math.abs(w) + 1) / Math.log(10))
    orderOfMag(x) == orderOfMag(y)

$("#buy_price,buy_quantity").keyup ->
    if not sputnik.canPlaceOrder(Number($("#buy_quantity").val()), Number($("#buy_price").val()), 'BTC/MXN', 'BUY')
        $("#buy_panel alert:visible").slideUp()
    else
        $("#buy_panel alert").slideDown()

$("#sell_price,#sell_quantity").keyup ->
    if not sputnik.canPlaceOrder(Number($("#sell_quantity").val()), Number($("#sell_price").val()), 'BTC/MXN', 'SELL')
        $("#sell_panel alert:visible").slideUp()
    else
        $("#sell_panel alert").slideDown()

$("#buyButton").click ->
    buy_quantity = Number($('#buy_quantity').val())
    buy_price = Number($("#buy_price").val())

    if buy_quantity == 0 or buy_price == 0
        return true

    if not withinAnOrderOfMagnitude(buy_price, best_bid.price)
        return if not confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?'

    sputnik.placeOrder(buy_quantity, buy_price, 'BTC/MXN', 'BUY')

$("#sellButton").click ->
    sell_quantity = Number($('#sell_quantity').val())
    sell_price = Number($("#sell_price").val())

    if sell_quantity == 0 or sell_price == 0
        return true

    if not withinAnOrderOfMagnitude(sell_price, best_ask.price)
        return if not confirm 'This price is significantly different from the latest market price.\n\nAre you sure you want to execute this trade?'

    sputnik.placeOrder(sell_quantity, sell_price, 'BTC/MXN', 'SELL')

$("#logout").click (event) ->
    document.cookie = ''
    sputnik.logout()
    location.reload()

$("#account").click (event) ->
    $("#account_modal").modal()

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

$('#deposit_mxn').click (event) ->
    $('#compropago_error').hide()
    $('#compropago_modal').modal()

$('#deposit_btc').click (event) ->
    sputnik.getAddress('BTC')
    $('#deposit_btc_modal').modal()

$('#withdraw_mxn').click (event) ->
    $('#withdraw_disabled_modal').modal()

$('#withdraw_btc').click (event) ->
    $('#withdraw_disabled_modal').modal()

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

    if (Number(amount) < 600)
      sputnik.makeCompropagoDeposit store, Number(amount), customer_email, send_sms, customer_phone, customer_phone_company

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
    updateTable "buys", data

    #todo: debounce with futility counter
    if not $("#sell_price").is(":focus") and not $("#sell_quantity").is(":focus")
      $("#sell_price").val best_bid.price

updateSells = (data) ->
    updateTable "sells", data
    #todo: debounce with futility counter
    if not $("#buy_price").is(":focus") and not $("#buy_quantity").is(":focus")
      $("#buy_price").val best_ask.price

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

    $('#audit_tab_select').click ->
        sputnik.getAudit()

    $('#ledger_tab_select').click ->
        sputnik.getLedgerHistory()

sputnik.on "trade_history", (trade_history) ->
    updateTrades(trade_history['BTC/MXN'])
    updatePlot(trade_history['BTC/MXN'])
    if trade_history.length > 0
        $('#last').text trade_history[trade_history.length - 1].price.toFixed(0)

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
    if book.contract is not "BTC/MXN"
        return

    if book.asks.length
        window.best_ask = book.asks[0]
    if book.bids.length
        window.best_bid = book.bids[0]

    updateBuys ([book_row.price, book_row.quantity] for book_row in book.bids)
    updateSells ([book_row.price, book_row.quantity] for book_row in book.asks)

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

sputnik.on "place_order_fail", (error) ->
    alert "order placement failed: #{error[1]}"

sputnik.on "profile", (profile) ->
    $('#new_nickname').val profile.nickname
    $('#new_email').val profile.email

sputnik.on "audit_details", (audit_details) ->
    $('#audit_details').text JSON.stringify(audit_details, undefined, 2)

sputnik.on "audit_hash", (audit_hash) ->
    $('#audit_hash').text audit_hash

sputnik.on "ledger_history", (ledger_history) ->
    $('#ledger_history').text JSON.stringify(ledger_history, null, 4)
