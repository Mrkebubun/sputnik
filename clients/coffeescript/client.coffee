# Copyright (c) 2014, Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

Sputnik = require("./sputnik").Sputnik

sputnik = new Sputnik "ws://127.0.0.1:8880/ws"
sputnik.connect()
got_cookie = false
sputnik.on "log", console.log
sputnik.on "warn", console.log
sputnik.on "error", console.log
sputnik.on "open", (session, details) ->
    console.log "Sputnik session open."
    #sputnik.follow "NETS2014"
    sputnik.authenticate "marketmaker", "marketmaker"

sputnik.on "auth_success", ->
    console.log "Authenticated"
    if not got_cookie
        sputnik.getCookie()
    else
        sputnik.changePassword "marketmaker", "marketmaker"

sputnik.on "auth_fail", ->
    console.log "Cannot login"

sputnik.on "cookie", (cookie) ->
    got_cookie = true
    sputnik.restoreSession "marketmaker", cookie

