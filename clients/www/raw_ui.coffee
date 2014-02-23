location = window.location
hostname = location.hostname
protocol = location.protocol
if protocol == 'http:'
    ws_protocol = "ws:"
else
    ws_protocol = "wss:"

uri = ws_protocol + "//" + hostname + ":8000"

sputnik = new window.Sputnik uri
sputnik.connect()

# Register UI events
$('#chatButton').click ->
    chat_return = sputnik.chat chatBox.value
    if not chat_return[0]
        alert chat_return[1]

    $('#chatBox').val('')

$('#loginButton').click ->
    sputnik.authenticate login.value, password.value

$('#logoutButton').click ->
    # Clear cookie
    document.cookie = ''
    sputnik.logout()

$('#registerButton').click ->
    sputnik.makeAccount registerLogin.value, registerPassword.value, registerEmail.value

$('#changeProfileBtn').click ->
    sputnik.changeProfile(newNickname.value, newEmail.value)

$('#sellButton').click ->
    sputnik.placeOrder(Number(qsell.value), Number(psell.value), ticker.value, 'SELL')

$('#buyButton').click ->
    sputnik.placeOrder(Number(qbuy.value), Number(pbuy.value), ticker.value, 'BUY')

$('#cancelButton').click ->
    sputnik.cancelOrder(parseInt(orderId.value))

clearTable = (table) ->
    while table.hasChildNodes()
        table.removeChild(table.firstChild)

# UI functions
displayMarkets = (markets) ->
    # Why are we doing [0] here? This is not clear to me
    table = $('#marketsTable')[0]
    clearTable(table)
    header = table.insertRow(-1)
    header.insertCell(-1).innerText = "Contract"
    header.insertCell(-1).innerText = "Description"
    header.insertCell(-1).innerText = "Full Description"
    header.insertCell(-1).innerText = "Contract Type"
    header.insertCell(-1).innerText = "Tick Size"
    header.insertCell(-1).innerText = "Lot Size"
    header.insertCell(-1).innerText = "Denominator"
    for ticker, data of markets
        row = table.insertRow(-1)
        row.insertCell(-1).innerText = ticker
        row.insertCell(-1).innerText = data.description
        row.insertCell(-1).innerText = data.full_description
        row.insertCell(-1).innerText = data.contract_type
        row.insertCell(-1).innerText = data.tick_size
        row.insertCell(-1).innerText = data.lot_size
        row.insertCell(-1).innerText = data.denominator

generateBookTable = (book) ->
    table = document.createElement('table')
    header = table.insertRow(-1)
    header.insertCell(-1).innerText = "Price"
    header.insertCell(-1).innerText = "Quantity"
    for book_row in book
        row = table.insertRow(-1)
        row.insertCell(-1).innerText = book_row.price
        row.insertCell(-1).innerText = book_row.quantity

    return table


displayBooks = (books) ->
    table = $('#booksTable')[0]
    clearTable(table)
    header = table.insertRow(-1)
    header.insertCell(-1).innerText = "Contract"
    header.insertCell(-1).innerText = "Bids"
    header.insertCell(-1).innerText = "Asks"
    for ticker, data of books
        if data.contract_type != "cash"
            row = table.insertRow(-1)
            row.insertCell(-1).innerText = ticker
            row.insertCell(-1).appendChild(generateBookTable(data.bids))
            row.insertCell(-1).appendChild(generateBookTable(data.asks))

displayPositions = (positions) ->
    table = $('#positionsTable')[0]
    clearTable(table)
    header = table.insertRow(-1)
    header.insertCell(-1).innerText = "Contract"
    header.insertCell(-1).innerText = "Position"
    header.insertCell(-1).innerText = "Reference Price"
    for id, position of positions
        row = table.insertRow(-1)
        row.insertCell(-1).innerText = position.contract
        row.insertCell(-1).innerText = position.position
        row.insertCell(-1).innerText = position.reference_price

displayOrders = (orders) ->
    table = $('#ordersTable')[0]
    clearTable(table)
    header = table.insertRow(-1)
    header.insertCell(-1).innerText = "Contract"
    header.insertCell(-1).innerText = "Price"
    header.insertCell(-1).innerText = "Quantity"
    header.insertCell(-1).innerText = "Quantity Left"
    header.insertCell(-1).innerText = "Side"
    header.insertCell(-1).innerText = "TimeStamp"
    header.insertCell(-1).innerText = "Id"
    for id, order of orders
        row = table.insertRow(-1)
        row.insertCell(-1).innerText = order.contract
        row.insertCell(-1).innerText = order.price
        row.insertCell(-1).innerText = order.quantity
        row.insertCell(-1).innerText = order.quantity_left
        row.insertCell(-1).innerText = order.side
        row.insertCell(-1).innerText = order.timestamp
        row.insertCell(-1).innerText = id

# Handle emitted events
sputnik.on "open", ->
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

sputnik.on "close", ->
    # location.reload()

sputnik.on "session_expired", ->
    console.log "Session is stale."
    document.cookie = ''

sputnik.on "markets", (markets) ->
    for ticker, data of markets
        if data.contract_type != "cash"
            sputnik.follow ticker
            sputnik.getOrderBook ticker

    displayMarkets markets

sputnik.on "positions", (positions) ->
    displayPositions positions

sputnik.on "orders", (orders) ->
    displayOrders orders

sputnik.on "book", (book) ->
    displayBooks book

sputnik.on "chat", (chat_messages) ->
    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "auth_success", (username) ->
    sputnik.getCookie()
    sputnik.log "username: " + username
    $('#loggedInAs').text("Logged in as " + username)

sputnik.on "cookie", (uid) ->
    sputnik.log "cookie: " + uid
    document.cookie = "login" + "=" + login.value + ":" + uid

sputnik.on "auth_fail", (error) ->
    sputnik.error "login error: #{error.desc}"
    alert "login error: #{error.desc}"
    document.cookie = ""

sputnik.on "profile", (profile) ->
    sputnik.log "profile: " + profile.nickname + " " + profile.email
    $('#nickname').text(profile.nickname)
    $('#email').text(profile.email)

sputnik.on "wtf", (error) ->
    # There was a serious error. It is probably best to reconnect.
    sputnik.error "GUI: #{error}"
    alert error
    sputnik.close()

sputnik.on "make_account_success", (username) ->
    sputnik.log "make_account success: #{username}"
    alert "account creation success: #{username}"

sputnik.on "make_account_fail", (error) ->
    sputnik.error "make_account_fail: #{error}"
    alert "account creation failed: #{error}"

sputnik.on "logout", () ->
    sputnik.log "loggedout"
    $('#loggedInAs').text('Not logged in')

sputnik.on "place_order", () ->
    sputnik.log "GUI: placing order"

sputnik.on "place_order_success", (res) ->
    sputnik.log "place order success: #{res.desc}"
    alert "success: #{res.desc}"

sputnik.on "place_order_fail", (error) ->
    sputnik.log "place order fail: #{error}"
    alert "error: #{error}"

###
# feedLog
sputnik.on "fill", (trade) ->
  sputnik.log "fill: #{trade}"
  table = $('#feedLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "Fill"
  row.insertCell(-1).innerText = "contract: #{trade.contract} price: #{trade.price} quantity: #{trade.quantity} side: #{trade.side} id: #{trade.id} timestamp: #{trade.timestamp}"

sputnik.on "order", (order) ->
  sputnik.log "order: #{order}"
  table = $('#feedLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "Order"
  row.insertCell(-1).innerText = "contract: #{order.contract} price: #{order.price} quantity: #{order.quantity} quantity_left: #{order.quantity_left} side: #{order.side} timestamp: #{order.timestamp} is_cancelled: #{order.is_cancelled}"

sputnik.on "trade", (trade) ->
  sputnik.log "trade: #{trade}"
  table = $('#feedLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "Trade"
  row.insertCell(-1).innerText = "contract: #{trade.contract} price: #{trade.price} quantity: #{trade.quantity} timestamp: #{trade.timestamp}"

# debugLog
sputnik.on "log", (obj) ->
  table = $('#debugLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "log: #{obj}"

sputnik.on "warn", (obj) ->
  table = $('#debugLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "warn: #{obj}"

sputnik.on "error", (obj) ->
  table = $('#debugLog')[0]
  row = table.insertRow(-1)
  row.insertCell(-1).innerText = "error: #{obj}"
###
