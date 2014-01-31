### UI API ###

class Sputnik extends EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}
    logged_in: false
    authextra: {}
    chat_messages: []

    constructor: (@uri) ->


    ### Sputnik API  ###

    # network control
    
    connect: () =>
        ab.connect @uri, @onOpen, @onClose

    close: () =>
        @session?.close()

    # market selection
    
    follow: (market) =>
        if not @session?
            return @wtf "Not connected."
        @subscribe "order_book##{market}", @onBookUpdate
        @subscribe "trades##{market}", @onTrade

    unfollow: (market) =>
        if not @session?
            return @wtf "Not connected."
        @unsubscribe "order_book##{market}"
        @unsubscribe "trades##{market}"

    # authentication and account management

    makeAccount: (username, password, email) =>
        if not @session?
            return @wtf "Not connected"

        @log("makeAccount")

        @log("computing salt")
        salt = Math.random().toString(36).slice(2)
        @log("computing hash")
        @authextra['salt'] = salt;
        password_hash = ab.deriveKey(password, @authextra);

        @log('making session call for makeAccount');
        @call("make_account", name, password_hash, salt,  email).then \
          (res) =>
            @log('account created: #{name}')
            login.value = registerLogin.value;
            @authenticate(registerLogin.value, registerPassword.value)
          , (error) =>
            @emit "make_account_error", error


    getProfile: () =>
      if not @session?
        return @wtf "Not connected"

      @call("get_profile").then \
        (profile) =>
            @emit "profile", profile.nickname, profile.email

    changeProfile: (nickname, email) =>
      if not @session?
        return @wtf "Not connected"

      @call("change_profile", nickname, email).then \
        (res) =>
          @getProfile()

    failed_login: (error) =>
      @emit "failed_login", error

    authenticate: (login, password) =>
      @session.authreq(login).then \
        (challenge) =>
          @authextra = JSON.parse(challenge).authextra
          @log('challenge', @authextra)
          @log(ab.deriveKey(password, @authextra))

          secret = ab.deriveKey(password, @authextra)
          @log(challenge)
          signature = @session.authsign(challenge, secret)
          @log(signature)
          @session.auth(signature).then(@onAuth, @failed_login)
          @log('authenticate');
      , (error) ->
        @failed_login(error);

    cookie_login: (cookie) =>
      parts = cookie.split("=", 2)[1].split(":", 2)
      name = parts[0]
      uid = parts[1]
      if !uid
        return @failed_cookie "bad_cookie, clearing"

      @session.authreq(uid).then \
        (challenge) =>
          @authextra = JSON.parse(challenge).authextra
          @authextra.salt = "cookie"
          secret = ab.deriveKey("cookie", @authextra)
          signature = @session.authsign(challenge, secret)
          @log signature
          @session.auth(signature).then \
            (permissions) =>
              login.value = name
              @onAuth permissions
            , @failed_cookie
          @log "end of cookie login"
        , (error) =>
          @failed_cookie "error processing cookie login: #{error}"

    failed_cookie: (error) =>
      document.cookie = ''
      @emit "failed_cookie", error
      @log error

    logout: () =>
      @logged_in = false

      # Clear user data
      @site_positions = []
      @open_orders = []
      @authextra =
                   "keylen": 32
                   "salt": "RANDOM_SALT"
                   "iterations": 1000
      @log @open_orders

      # TODO: Unsubscribe from everything
      @call "logout"

      # Clear cookie
      document.cookie = ''
      @close()
      @connect()
      @emit "logout"

    getCookie: () =>
      @call("get_cookie").then \
        (uid) =>
          @log("cookie: " + uid)
          document.cookie = "login" + "=" + login.value + ":" + uid

    onAuth: (permissions) =>
      ab.log("authenticated!", JSON.stringify(permissions));
      @logged_in = true;

      @getCookie()
      @getProfile()
      @getSafePrices()
      @getOpenOrders()
      @getPositions()

      @user_id = (x.uri for x in permissions.pubsub)[1].split('#')[1]
      @emit "loggedIn", @user_id

      try
        @subscribe "cancels#" + @user_id, @onCancel
      catch error
        @log error

      try
        @subscribe "fills#" + @user_id, @onFill
      catch error
        @log error

      try
        @subscribe "open_orders#" + @user_id, @onOpenOrder
      catch error
        @log error

      #@switchBookSub SITE_TICKER

    # order manipulation
    
    placeOrder: (quantity, price, ticker, side) =>
      order =
        quantity: quantity
        price: price
        ticker: ticker
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
      @call("cancel_order", id)


    # deposits and withdrawals

    getAddress: (contract) =>
    newAddress: (contract) =>
    withdraw: (contract, address, amount) =>

    # account/position information
    getSafePrices: () =>
    getOpenOrders: () =>
      @log("getting open orders")
      @call("get_open_orders").then \
        (orders) =>
          @log("orders received: #{orders}")
          @emit "orders", orders

    getPositions: () =>
      @log("getting positions")
      @call("get_positions").then \
        (positions) =>
          @log("positions received: #{positions}")
          @emit "positions", positions

    # miscelaneous methods

    chat: (message) =>
      if @logged_in
        @publish "chat", message
        return [true, null]
      else
        return [false, "Not logged in"]

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
        @log "calling #{method} with #{params}"
        if not @session?
            return @wtf "Not connected."
        d = ab.Deferred()
        @session.call("#{@uri}/procedures/#{method}", params...).then \
            (result) =>
                if result.length != 2
                    @warn "RPC Warning: sputnik protocol violation"
                    return d.resolve result
                if result[0]
                    d.resolve result[1]
                else
                    d.reject result[1]
            ,(error) => @wtf "RPC Error: #{error.desc}"
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
        @emit "wtf_error", obj

    # connection events
    onOpen: (@session) =>
        @log "Connected to #{@uri}."

        @call("list_markets").then @onMarkets, @wtf
        @subscribe "chat", @onChat
        @call("get_chat_history").then \
          (chats) ->
            @chat_history = chats
            @emit "chat", @chat_history

        # Attempt a cookie login
        cookie = document.cookie
        @log "cookie: #{cookie}"
        if cookie
          @cookie_login cookie

    onClose: (code, reason, details) =>
        @log "Connection lost."
        @emit "close"

    # authentication internals
   
    # default RPC callbacks

    onMarkets: (@markets) =>
        for ticker of markets
            @markets[ticker].trades = []
            @markets[ticker].buys = []
            @markets[ticker].sells = []
        @emit "markets", @markets

 
    # public feeds
    onBookUpdate: (event) =>
        ticker = event.ticker
        @markets[ticker].buys = event.buys
        @markets[ticker].sells = event.sells
        @emit "book_update", @markets

    onTrade: (event) =>
        ticker = event.ticker
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
