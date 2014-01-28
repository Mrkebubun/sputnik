events = require "events"
window = require "./autobahn.node"
ab = window.ab

### UI API ###

class Sputnik extends events.EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}

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

    newAccount: (username, password, email) =>
        if not @session?
            return @wtf "Not connected."
        @call("make_account", username, password, email)

    getProfile: () =>
    changeProfile: (password, email, nickname) =>
    authenticate: (username, password) =>

    # order manipulation
    
    order: (ticker, price, quantity) =>
    cancel: (ticker, id) =>

    # deposits and withdrawals

    getAddress: (contract) =>
    newAddress: (contract) =>
    withdraw: (contract, address, amount) =>

    # miscelaneous methods

    chat: (message) =>

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
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

sputnik = new Sputnik "wss://sputnikmkt.com:8000"
sputnik.connect()

sputnik.on "ready", ->
        sputnik.follow "MXN/BTC"
        sputnik.on "chat", ([user, message]) ->
            console.log "GUI: #{user}: #{message}"

sputnik.on "error", (error) ->
    # There was an RPC error. It is probably best to reconnect.
    console.error "GUI: #{error}"
    sputnik.close()

