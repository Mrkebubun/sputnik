### UI API ###

class window.Sputnik extends EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}
    authenticated: false
    profile:
        email: null
        nickname: null
    chat_messages: []

    constructor: (@uri) ->


    ### Sputnik API  ###

    # network control
    
    connect: () =>
        ab.connect @uri, @onOpen, @onClose

    close: () =>
        @session?.close()
        @session = null

    # market selection
    
    follow: (market) =>
        @subscribe "order_book##{market}", @onBookUpdate
        @subscribe "trades##{market}", @onTrade

    unfollow: (market) =>
        @unsubscribe "order_book##{market}"
        @unsubscribe "trades##{market}"

    # authentication and account management

    makeAccount: (username, secret, email) =>
        @log "Computing password hash..."
        salt = Math.random().toString(36).slice(2)
        authextra =
            salt: salt
            iterations: 1000
        password = salt + ":" + ab.deriveKey secret, authextra

        @call("make_account", username, password, email).then \
          (result) =>
            @emit "make_account_success", result
          , (error) =>
            @emit "make_account_error", error

    getProfile: () =>
      @call("get_profile").then (@profile) =>
        @emit "profile", @profile

    changeProfile: (nickname, email) =>
      @call("change_profile", email, nickname).then (@profile) =>

    authenticate: (login, password) =>
        if not @session?
            @wtf "Not connected."

        @session.authreq(login).then \
            (challenge) =>
                authextra = JSON.parse(challenge).authextra
                secret = ab.deriveKey(password, authextra)
                signature = @session.authsign(challenge, secret)
                @session.auth(signature).then @onAuthSuccess, @onAuthFail
            , (error) =>
                @emit "Failed login: Could not authenticate: #{error}."
    
    restoreSession: (uid) =>
        if not @session?
            @wtf "Not connected."

        @session.authreq(uid).then \
            (challenge) =>
                # TODO: Why is this secret hardcoded?
                secret = "EOcGpbPeYMMpL5hQH/fI5lb4Pn2vePsOddtY5xM+Zxs="
                signature = @session.authsign(challenge, secret)
                @session.auth(signature).then @onAuthSuccess, @onSessionExpired
            , (error) =>
                @wtf "RPC Error: Could not authenticate: #{error}."

    logout: () =>
        @authenticated = false
        @call "logout"
        @close()
        @emit "logout"

    getCookie: () =>
      @call("get_cookie").then \
        (uid) =>
          @log("cookie: " + uid)
          @emit "cookie", uid

    onAuthSuccess: (permissions) =>
      ab.log("authenticated!", JSON.stringify(permissions))
      @authenticated = true

      @getProfile()
      @getSafePrices()
      @getOpenOrders()
      @getPositions()

      @username = permissions.username
      @emit "logged_in", @username

      try
        @subscribe "cancels#" + @username, @onCancel
      catch error
        @log error

      try
        @subscribe "fills#" + @username, @onFill
      catch error
        @log error

      try
        @subscribe "open_orders#" + @username, @onOpenOrder
      catch error
        @log error

    onAuthFail: (error) =>
        @username = null
        [code, reason] = error  
        @emit "failed_login", error

    onSessionExpired: (error) =>
        @emit "session_expired"

    # order manipulation
    
    placeOrder: (quantity, price, ticker, side) =>
      order =
        quantity: quantity
        price: price
        contract: ticker
        side: side
      @log "placing order: #{order}"
      @emit "place_order", order
      @call("place_order", order).then \
        (res) =>
          @emit "place_order_success", res
        , (error) =>
          @emit "place_order_error", error

    cancelOrder: (id) =>
      @log "cancelling: #{id}"
      @call("cancel_order", id).then \
        (ret) =>
          @emit "cancel_order", ret
        , (error) =>
          @emit "cancel_order_error", error

    # deposits and withdrawals

    getAddress: (contract) =>
    newAddress: (contract) =>
    withdraw: (contract, address, amount) =>

    # account/position information
    getSafePrices: () =>
    getOpenOrders: () =>
      @call("get_open_orders").then \
        (orders) =>
          @log("orders received: #{orders}")
          @emit "orders", orders

    getPositions: () =>
      @call("get_positions").then \
        (positions) =>
          @log("positions received: #{positions}")
          @emit "positions", positions

    getOrderBook: (ticker) =>
      @call("get_order_book", ticker).then @onBookUpdate

    # miscelaneous methods

    chat: (message) =>
      if @authenticated
        @publish "chat", message
        return [true, null]
      else
        return [false, "Not logged in"]

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
        if not @session?
            return @wtf "Not connected."
        @log "Invoking RPC #{method}(#{params})"
        d = ab.Deferred()
        @session.call("#{@uri}/procedures/#{method}", params...).then \
            (result) =>
                if result.length != 2
                    @warn "RPC Warning: sputnik protocol violation in #{method}"
                    return d.resolve result
                if result[0]
                    d.resolve result[1]
                else
                    d.reject result[1]
            ,(error) => @wtf "RPC Error: #{error.desc} in #{method}"
        return d.promise

    subscribe: (topic, callback) =>
        if not @session?
            return @wtf "Not connected."
        @session.subscribe "#{@uri}/user/#{topic}", (topic, event) -> callback event

    unsubscribe: (topic) =>
        if not @session?
            return @wtf "Not connected."
        @session.unsubscribe "#{@uri}/user/#{topic}"

    publish: (topic, message) =>
        if not @session?
          return @wtf "Not connected."
        @log "Publishing #{message} on #{topic}"
        @session.publish "#{@uri}/user/#{topic}", message

    # logging
    log: (obj) -> console.log obj
    warn: (obj) -> console.warn obj
    error: (obj) -> console.error obj
    wtf: (obj) => # What a Terrible Failure
        @error obj
        @emit "error", obj

    # connection events
    onOpen: (@session) =>
        @log "Connected to #{@uri}."

        @call("get_markets").then @onMarkets, @wtf
        @subscribe "chat", @onChat
        # TODO: Are chats private? Do we want them for authenticated users only?
        #@call("get_chat_history").then \
        #  (chats) ->
        #    @chat_history = chats
        #    @emit "chat", @chat_history

        @emit "open"

    onClose: (code, reason, details) =>
        @log "Connection lost."
        @emit "close"

    # authentication internals
   
    # default RPC callbacks

    onMarkets: (@markets) =>
        for ticker of markets
            @markets[ticker].trades = []
            @markets[ticker].bids = []
            @markets[ticker].asks = []
        @emit "markets", @markets

 
    # public feeds
    onBookUpdate: (event) =>
        ticker = event.contract
        @markets[ticker].bids = event.bids
        @markets[ticker].asks = event.asks
        @emit "book_update", @markets

    onTrade: (event) =>
        ticker = event.contract
        @markets[ticker].trades.push event
        @emit "trade", event

    onChat: (event) =>
        # TODO: Something is wrong where my own chats don't show up in this box-- but they do get sent
        user = event[0]
        message = event[1]
        @chat_messages.push "#{user}: #{message}"
        @log "Chat: #{user}: #{message}"
        @emit "chat", @chat_messages

    # private feeds
    onOrder = () =>
    onSafePrice = () =>

# Connect

sputnik = new Sputnik "ws://localhost:8000"
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
  sputnik.placeOrder(parseInt(qsell.value), parseInt(psell.value), ticker.value, 'SELL')

$('#buyButton').click ->
  sputnik.placeOrder(parseInt(qbuy.value), parseInt(pbuy.value), ticker.value, 'BUY')

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
  for contract, data of markets
    if data.contract_type != "cash"
      row = table.insertRow(-1)
      row.insertCell(-1).innerText = contract
      row.insertCell(-1).appendChild(generateBookTable(data.bids))
      row.insertCell(-1).appendChild(generateBookTable(data.asks))

displayPositions = (positions) ->
  table = $('#positionsTable')[0]
  for id, position of positions
    row = table.insertRow(-1)
    row.insertCell(-1).innerText = position.contract
    row.insertCell(-1).innerText = position.position
    row.insertCell(-1).innerText = position.reference_price

displayOrders = (orders) ->
  table = $('#ordersTable')[0]
  for order in orders
    row = table.insertRow(-1)
    row.insertCell(-1).innerText = order.contract
    row.insertCell(-1).innerText = order.price
    row.insertCell(-1).innerText = order.quantity
    row.insertCell(-1).innerText = order.quantity_left
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

sputnik.on "book_update", (markets) ->
  displayBooks markets

sputnik.on "positions", (positions) ->
  displayPositions positions

sputnik.on "orders", (orders) ->
  displayOrders orders

sputnik.on "chat", (chat_messages) ->
    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "loggedIn", (user_id) ->
  login.value = user_id
  sputnik.log "userid: " + user_id
  $('#loggedInAs').text("Logged in as " + user_id)

sputnik.on "profile", (nickname, email) ->
  sputnik.log "profile: " + nickname + " " + email
  $('#nickname').text(nickname)
  $('#email').text(email)

sputnik.on "wtf_error", (error) ->
    # There was a serious error. It is probably best to reconnect.
    sputnik.error "GUI: #{error}"
    alert error
    sputnik.close()

sputnik.on "failed_login", (error) ->
  sputnik.error "login error: #{error.desc}"
  alert "login error: #{error.desc}"

sputnik.on "failed_cookie", (error) ->
  sputnik.error "cookie error: #{error.desc}"
  alert "cookie error: #{error.desc}"

sputnik.on "make_account_success", (username) ->
  sputnik.log "make_account success: #{username}"
  alert "account creation success: #{username}"

sputnik.on "make_account_error", (error) ->
  sputnik.error "make_account_error: #{error}"
  alert "account creation failed: #{error}"

sputnik.on "logout", () ->
  sputnik.log "loggedout"
  $('#loggedInAs').text('')

sputnik.on "place_order", () ->
  sputnik.log "GUI: placing order"

sputnik.on "place_order_success", (res) ->
  sputnik.log "place order success: #{res.desc}"
  alert "success: #{res.desc}"

sputnik.on "place_order_error", (error) ->
  sputnik.log "place order error: #{error}"
  alert "error: #{error}"
