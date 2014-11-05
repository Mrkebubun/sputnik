Sputnik = require("./sputnik").Sputnik

sputnik = new Sputnik "wss://demo.m2.io:8000"
sputnik.connect()
sputnik.on "open", ->
    console.log "Sputnik session open."
    sputnik.getOrderBook "BTC/MXN"
    sputnik.follow "BTC/MXN"
    sputnik.authenticate "a", "a"

sputnik.on "auth_success", ->
    console.log "Authenticated"

sputnik.on "auth_fail", ->
    console.log "Cannot login"

