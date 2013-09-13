WebSocket = require "ws"
uuid = require "node-uuid"
events = require "events"
promise  = require "node-promise"
crypto = require("cryptojs").Crypto

class Client extends events.EventEmitter
    TYPE_ID_WELCOME: 0
    TYPE_ID_PREFIX: 1
    TYPE_ID_CALL: 2
    TYPE_ID_CALLRESULT: 3
    TYPE_ID_CALLERROR: 4
    TYPE_ID_SUBSCRIBE: 5
    TYPE_ID_UNSUBSCRIBE: 6
    TYPE_ID_PUBLISH: 7
    TYPE_ID_EVENT: 8

    URI_WAMP_PROCEDURE: "http://api.wamp.ws/procedure#"

    constructor: (@uri, @debug=true) ->
        @state = "wait"
        @calls = {}
        @socket = new WebSocket @uri, protocol: "wamp"
        @socket.on "error", @error
        @socket.on "message", @message

    message: (m, flags) =>
        if @debug
            console.log "WAMP RX: ", m
        if @state is "closed"
            return
        try
            tokens = JSON.parse m
        catch e
            return @error "Protocol error: received malformed JSON data."
        if not Array.isArray tokens
            return @error "Procotol error: received data is not an array."
        if tokens.length == 0
            return @error "Protocol error: received array is empty."

        if @state isnt "open"
            if tokens[0] isnt @TYPE_ID_WELCOME
                return @error "Procotol error: did not receive a welcome."
            if tokens.length isnt 4
                return @error "Procotol error: malformed welcome message."
            [type, @sessionId, @protocolVersion, @serverIdent] = tokens
            @state = "open"
            return @emit "open"

        switch tokens[0]
            when @TYPE_ID_CALLRESULT
                if tokens.length isnt 3
                    return @error "Protocol error: malformed result."
                [type, id, result] = tokens
                @calls[id].resolve result
                delete @calls[id]
            when @TYPE_ID_CALLERROR
                if tokens.length < 4
                    return @error "Protocol error: malformed error."
                [type, id, uri, desc, details] = tokens
                @calls[id].reject uri, desc, details
                delete @calls[id]
            when @TYPE_ID_EVENT
                if tokens.length isnt 3
                    return @error "Protocol error: malformed event."
                [type, uri, event] = tokens
                @emit "event", uri, event
            else
                @error "Procotol error: unrecognized message type."

    send: (m) =>
        if @debug
            console.log "WAMP TX: ", m
        @socket.send JSON.stringify(m), @error

    error: (e) =>
        if not e?
            return
        @state = "closed"
        @socket.close()
        @emit "error", e

    prefix: (prefix, uri) =>
        @send [@TYPE_ID_PREFIX, prefix, uri]

    call: (uri, args...) =>
        id = uuid.v1()
        @send [@TYPE_ID_CALL, id, uri, args...]
        @calls[id] = promise.defer()
        return @calls[id].promise
    
    subscribe: (uri) =>
        @send [@TYPE_ID_SUBSCRIBE, uri]

    unsubscribe: (uri) =>
        @send [@TYPE_ID_UNSUBSCRIBE, uri]

    publish: (uri, event=null, exclude, eligible) =>
        if eligible?
            exclude = exclude or []
            @send [@TYPE_ID_PUBLISH, uri, event, exclude, eligible]
        else if exclude?
            @send [@TYPE_ID_PUBLISH, uri, event, exclude]
        else
            @send [@TYPE_ID_PUBLISH, uri, event]

    deriveKey: (secret, extra, callback) ->
        if extra?.salt
            salt = extra.salt
            iterations = extra.iterations or 10000
            keylen = extra.keylen or 32
            secret = crypto.PBKDF2 secret, salt, keylen,
                    iterations: iterations
                    hasher: crypto.SHA256
                    asBytes: true
            Buffer(secret).toString "base64"
        else
            secret

    handleAuth: (challenge, authSecret, d) =>
        challenge_obj = JSON.parse challenge
        authSecret = @deriveKey authSecret, challenge_obj.authextra
        hmac = crypto.HMAC crypto.SHA256, challenge, authSecret, asBytes: true
        sig =  Buffer(hmac).toString "base64"
        reply = @call @URI_WAMP_PROCEDURE + "auth", sig
        d.resolve reply

    authenticate: (authKey, authExtra, authSecret) =>
        d = promise.defer()
        reply = @call @URI_WAMP_PROCEDURE + "authreq", authKey, authExtra
        reply.addCallback (challenge) => @handleAuth challenge, authSecret, d
        reply.addErrback @error
        
module.exports = Client: Client

