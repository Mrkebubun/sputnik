### UI API ###

class window.Sputnik extends EventEmitter

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
    
    connect: () ->
        ab.connect @uri, @onOpen, @onClose

    close: () =>
        @session?.close()

    # market selection
    
    follow: (market) =>
        @subscribe "order_book##{market}", @onBookUpdate
        @subscribe "trades##{market}", @onTrade

    unfollow: (market) =>
        @unsubscribe "order_book##{market}"
        @unsubscribe "trades##{market}"

    # authentication and account management

    makeAccount: (username, secret, email) =>
        salt = Math.random().toString(36).slice(2)
        @authextra.salt = salt
        @authextra.iterations = 1000
        @log "Computing password hash..."
        password = salt + ":" + ab.deriveKey secret, @authextra

        @call("make_account", username, password, email)

    getProfile: () =>
      @call("get_profile")

    changeProfile: (nickname, email) =>
      @call("change_profile", email, nickname)

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
          @log('authenticate')
      , (error) ->
        @failed_login(error)

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
      ab.log("authenticated!", JSON.stringify(permissions))
      @logged_in = true

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
      @call("cancel_order", id)


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
      if @logged_in
        @publish "chat", message
        return [true, null]
      else
        return [false, "Not logged in"]

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
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
        @session.subscribe "#{@uri}/user/#{topic}", (topic, event) -> callback event

    unsubscribe: (topic) =>
        @session.unsubscribe "#{@uri}/user/#{topic}"

    publish: (topic, message) =>
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

