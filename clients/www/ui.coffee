sputnik = new window.Sputnik "ws://localhost:8000"
sputnik.connect()

# Register UI events
$('#chatButton').click ->
  chat_return = sputnik.chat chatBox.value
  if not chat_return[0]
    alert(chat_return[1])

  $('#chatBox').val('')

$('#loginButton').click ->
  sputnik.authenticate login.value, password.value

$('#logoutButton').click ->
  sputnik.logout()

$('#registerButton').click ->
  sputnik.makeAccount registerLogin.value, registerPassword.value, registerEmail.value

$('#changeProfileBtn').click ->
  sputnik.changeProfile(newNickname.value, newEmail.value)

$('#sellButton').click ->
  sputnik.placeOrder(parseInt(qsell.value), parseInt(psell.value), ticker.value, 1)

$('#buyButton').click ->
  sputnik.placeOrder(parseInt(qbuy.value), parseInt(pbuy.value), ticker.value, 0)

$('#cancelButton').click ->
  sputnik.cancelOrder(parseInt(orderId.value))

# UI functions
displayMarkets = (markets) ->
  # Why are we doing [0] here? This is not clear to me
  table = $('#marketsTable')[0]
  for ticker, data of markets
    if data.contract_type != "cash"
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
  for book_row in book
    row = table.insertRow(-1)
    row.insertCell(-1).innerText = book_row[0]
    row.insertCell(-1).innerText = book_row[1]

  return table

displayBooks = (markets) ->
  table = $('#booksTable')[0]
  for ticker, data of markets
    if data.contract_type != "cash"
      row = table.insertRow(-1)
      row.insertCell(-1).innerText = ticker
      row.insertCell(-1).appendChild(generateBookTable(data.sells))
      row.insertCell(-1).appendChild(generateBookTable(data.buys))

displayPositions = (positions) ->
  table = $('#positionsTable')[0]
  for id, position of positions
    row = table.insertRow(-1)
    row.insertCell(-1).innerText = position.ticker
    row.insertCell(-1).innerText = position.position
    row.insertCell(-1).innerText = position.reference_price

displayOrders = (orders) ->
  table = $('#ordersTable')[0]
  for order in orders
    row = table.insertRow(-1)
    row.insertCell(-1).innerText = order.ticker
    row.insertCell(-1).innerText = order.price
    row.insertCell(-1).innerText = order.quantity
    row.insertCell(-1).innerText = order.side
    row.insertCell(-1).innerText = order.timestamp
    row.insertCell(-1).innerText = order.id

# Handle emitted events
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

sputnik.on "chat", (chat_messages) ->
    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "loggedIn", (user_id) ->
  @log "userid: " + user_id
  $('#loggedInAs').text("Logged in as " + user_id)

sputnik.on "profile", (nickname, email) ->
  @log "profile: " + nickname + " " + email
  $('#nickname').text(nickname)
  $('#email').text(email)

sputnik.on "wtf_error", (error) ->
    # There was a serious error. It is probably best to reconnect.
    @error "GUI: #{error}"
    alert error
    sputnik.close()

sputnik.on "failed_login", (error) ->
  @error "login error: #{error.desc}"
  alert "login error: #{error.desc}"

sputnik.on "failed_cookie", (error) ->
  @error "cookie error: #{error.desc}"
  alert "cookie error: #{error.desc}"

sputnik.on "make_account_error", (error) ->
  @error "make_account_error: #{error}"
  alert "account creation failed: #{error}"

sputnik.on "logout", () ->
  @log "loggedout"
  $('#loggedInAs').text('')

sputnik.on "place_order", () ->
  @log "GUI: placing order"

sputnik.on "place_order_success", (res) ->
  @log "place order success: #{res.desc}"
  alert "success: #{res.desc}"

sputnik.on "place_order_error", (error) ->
  @log "place order error: #{error}"
  alert "error: #{error}"
