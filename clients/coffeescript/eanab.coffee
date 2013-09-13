wamp = require "./wamp"

client = new wamp.Client "ws://localhost:9000/"
client.on "error", (e) -> console.error e
client.on "open", () ->
    client.authenticate "username", null, "password"
