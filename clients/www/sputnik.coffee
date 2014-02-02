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

        @call("make_account", username, password, email)

    getProfile: () =>
      @call("get_profile").then (@profile) =>

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
                @wtf "RPC Error: Could not authenticate: #{error}."
    
    restoreSession: (uid) =>
        if not @session?
            @wtf "Not connected."

        @session.authreq(uid).then \
            (challenge) =>
                secret = "EOcGpbPeYMMpL5hQH/fI5lb4Pn2vePsOddtY5xM+Zxs="
                signature = @session.authsign(challenge, secret)
                @session.auth(signature).then @onAuthSuccess, @onSessionExpired
            , (error) =>
                @wtf "RPC Error: Could not authenticate: #{error}."

    logout: () =>
        @authenticated = false
        @call "logout"
        @close()

    getCookie: () =>
      @call("get_cookie")

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

        @call("list_markets").then @onMarkets, @wtf
        @subscribe "chat", @onChat
        @call("get_chat_history").then \
          (chats) ->
            @chat_history = chats
            @emit "chat", @chat_history

        @emit "open"

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

