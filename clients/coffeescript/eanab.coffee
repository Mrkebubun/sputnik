wamp = require "./wamp"

client = new wamp.Client "ws://localhost:9000/", debug=true
client.on "error", (e) -> console.error e
client.on "open", () ->
    console.log "session opened"
    promise = client.authenticate "fuck", "fuck"
    promise.then (result) ->
            console.log "authenticated"
            client.subscribe "http://example.com/user/cancels#fuck"
        , (error) ->
            console.error error[1]
client.on "close", () ->
    console.log "session closed"

