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
        password = ab.deriveKey secret, authextra

        @call("make_account", username, password, salt, email).then \
          (result) =>
            @emit "make_account_success", result
          , (error) =>
            @emit "make_account_fail", error

    getProfile: () =>
      @call("get_profile").then (@profile) =>
        @emit "profile", @profile

    changeProfile: (nickname, email) =>
      @call("change_profile", email, nickname).then (@profile) =>
        @emit "profile", @profile

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
                @wtf "Failed login: Could not authenticate: #{error}."
    
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
      @emit "auth_success", @username

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
        @emit "auth_fail", error

    onSessionExpired: (error) =>
        @emit "session_expired"

    onCancel: (event) =>
      @emit "cancel", event

    onFill: (event) =>
      @emit "fill", event

    onOpenOrder: (event) =>
      @emit "open_order", event

    # data conversion

    cstFromTicker: (ticker) =>
        contract = @markets[ticker]
        if contract.contract_type is "cash_pair"
            [s, t] = ticker.split("/")
            source = @markets[s]
            target = @markets[t]
        else
            source = @markets["BTC"]
            target = @markets[ticker]
        return [contract, source, target]

    positionFromWire: (wire_position) =>
      ticker = wire_position.contract
      position = wire_position
      position.position = @quantityFromWire(ticker, wire_position.position)
      position.reference_price = @priceFromWire(ticker, wire_position.reference_price)
      return position

    orderToWire: (order) =>
      ticker = order.contract
      wire_order = order
      wire_order.price = @priceToWire(ticker, order.price)
      wire_order.quantity = @quantityToWire(ticker, order.quantity)
      wire_order.quantity_left = @quantityToWire(ticker, order.quantity_left)
      return wire_order

    orderFromWire: (wire_order) =>
      ticker = wire_order.contract
      order = wire_order
      order.price = @priceFromWire(ticker, wire_order.price)
      order.quantity = @quantityFromWire(ticker, wire_order.quantity)
      order.quantity_left = @quantityFromWire(ticker, wire_order.quantity_left)
      return order

    quantityToWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)
        quantity = quantity * target.denominator
        quantity = quantity - quantity % contract.lot_size
        return quantity

    priceToWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)
        price = price * source.denominator * contract.denominator
        price = price - price % contract.tick_size
        return price
       
    quantityFromWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)
        
        return quantity / target.denominator
    
    priceFromWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)
        
        return price / (source.denominator * contract.denominator)

    getPricePrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)
        
        return Math.log(source.denominator / contract.tick_size) / Math.LN10
       
    getQuantityPrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)
      
        # TODO: account for contract denominator
        return Math.log(target.denominator / contract.lot_size) / Math.LN10
 

    # order manipulation

 
    placeOrder: (quantity, price, ticker, side) =>
      order =
        quantity: quantity
        price: price
        contract: ticker
        side: side
      @log "placing order: #{order}"
      @call("place_order", @orderToWire(order)).then \
        (res) =>
          @emit "place_order_success", res
        , (error) =>
          @emit "place_order_fail", error

    cancelOrder: (id) =>
      @log "cancelling: #{id}"
      @call("cancel_order", id).then \
        (ret) =>
          @emit "cancel_order", ret
        , (error) =>
          @emit "cancel_order_fail", error

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
        (wire_positions) =>
          @log("positions received: #{wire_positions}")
          positions = {}
          for id, position of wire_positions
            positions[id] = @positionFromWire(position)
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
        books = {}
        for ticker of event
            @markets[ticker].bids =
                (order for order in event[ticker] when order.side is "BUY")
            @markets[ticker].asks =
                (order for order in event[ticker] when order.side is "SELL")
            books[ticker] =
              bids: (@orderFromWire(order) for order in @markets[ticker].bids)
              asks: (@orderFromWire(order) for order in @markets[ticker].asks)

        @emit "book_update", books

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

