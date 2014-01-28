### UI API ###

class Sputnik extends EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}
    logged_in: false
    authextra: {}

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

        console.log("makeAccount")

        salt = Math.random().toString(36).slice(2)
        @authextra['salt'] = salt;
        password_hash = ab.deriveKey(password, @authextra);

        @log('making session call for makeAccount');
        @call("make_account", name, password_hash, salt,  email).then \
          (res) ->
            login.value = registerLogin.value;
            @authenticate(registerLogin.value, registerPassword.value)

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
      alert(error)

    authenticate: (login, password) =>
      @session.authreq(login).then \
        (challenge) =>
          @authextra = JSON.parse(challenge).authextra
          console.log('challenge', @authextra)
          console.log(ab.deriveKey(password, @authextra))

          secret = ab.deriveKey(password, @authextra)
          console.log(challenge)
          signature = @session.authsign(challenge, secret)
          console.log(signature)
          @session.auth(signature).then(@onAuth, @failed_login)
          console.log('authenticate');
      , (error) ->
        @failed_login(error);

    getCookie: () =>
      @call("get_cookie").then \
        (uid) ->
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

      @user_id = _.pluck(permissions.pubsub, 'uri')[1].split('#')[1]
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

      @subscribe "chat", @onChat

      #@switchBookSub SITE_TICKER

    # order manipulation
    
    order: (ticker, price, quantity) =>
    cancel: (ticker, id) =>

    # deposits and withdrawals

    getAddress: (contract) =>
    newAddress: (contract) =>
    withdraw: (contract, address, amount) =>

    # account/position information
    getSafePrices: () =>
    getOpenOrders: () =>
    getPositions: () =>

    # miscelaneous methods

    chat: (message) =>
      @publish "chat", message

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

        # @emit "open"
    
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
        @emit "ready"

 
    # public feeds
    onBookUpdate: (event) =>
        ticker = event.ticker
        @markets[ticker].buys = event.buys
        @markets[ticker].sells = event.sells
        @emit "book_update", event

    onTrade: (event) =>
        ticker = event.ticker
        @markets[ticker].trades.push event
        @emit "trade", event

    onChat: (event) =>
        @emit "chat", event

    # private feeds
    onOrder = () =>
    onSafePrice = () =>



sputnik = new Sputnik "ws://localhost:8000"
sputnik.connect()

# Register UI events
$('#chatButton').click ->
  sputnik.chat chatBox.value
  $('#chatBox').val('')

$('#loginButton').click ->
  sputnik.authenticate login.value, password.value

$('#registerButton').click ->
  sputnik.makeAccount registerLogin.value, registerPassword.value, registerEmail.value

$('#changeProfileBtn').click ->
  sputnik.changeProfile(newNickname.value, newEmail.value)

# Handle emitted events
sputnik.on "ready", ->
        sputnik.follow "MXN/BTC"

chat_messages = []
sputnik.on "chat", ([user, message]) ->
    console.log "chat: #{user}: #{message}"
    chat_messages.push "#{user}: #{message}"

    $('#chatArea').html(chat_messages.join("\n"))
    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);

sputnik.on "loggedIn", (user_id) ->
  console.log "userid: " + user_id
  $('#loggedInAs').text("Logged in as " + user_id)

sputnik.on "profile", (nickname, email) ->
  console.log "profile: " + nickname + " " + email
  $('#nickname').text(nickname)
  $('#email').text(email)

sputnik.on "error", (error) ->
    # There was an RPC error. It is probably best to reconnect.
    console.error "GUI: #{error}"
    alert(error)
    sputnik.close()

