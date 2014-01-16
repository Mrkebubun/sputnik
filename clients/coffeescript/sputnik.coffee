events = require "events"
ab = require "./autobahn.node"


### UI API ###

class Sputnik extends events.EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}

    constructor: (@uri) ->
        ab.connect @uri, @onOpen, @onClose


    ### Sputnik API  ###

    # market selection
    
    follow: (market) =>
        @session.subscribe "#{@uri}/order_book##{market}", (topic, event) =>
            @onBookUpdate event
        @session.subscribe "#{@uri}/trades##{market}", (topic, event) =>
            @onTrade event

    unfollow: (market) =>
        @session.unsubscribe "#{@uri}/order_book##{market}"
        @session.unsubscribe "#{@uri}/trades##{market}"

    # authentication and account management

    newAccount: (username, password, email, nickname) =>
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


    ### internal methods ###

    # logging
    log: (obj) -> console.log obj
    error: (obj) -> console.error obj
    wtf: (obj) => # What a Terrible Failure
        @error obj
        @emit "error", obj

    # connection events
    onOpen: (@session) =>
        @log "Connected to #{@uri}."

        @session.call("#{@uri}/procedures/list_markets").then @onMarkets, () =>
            @wtf "Could not get a list of active markets."

        @session.subscribe "#{@uri}/user/chat", (topic, event) =>@onChat event

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
sputnik.on "chat", ([user, message]) -> console.log "GUI: #{user}: #{message}"
sputnik.on "book_update", () -> console.log "GUI: #{sputnik.markets['MXN/BTC']}"
sputnik.on "error", (error) -> console.error "GUI: #{error}"

