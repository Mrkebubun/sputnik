jQuery.fn.serializeObject = ->
    arrayData = @serializeArray()
    objectData = {}
    $.each arrayData, ->
        if @value?
            value = @value
        else
            value = ''
        if objectData[@name]?
            unless objectData[@name].push
                objectData[@name] = [objectData[@name]]
            objectData[@name].push value
        else
            objectData[@name] = value
    return objectData

@compliance_client_handler = (form) ->
    sputnik.getRequestSupportNonce 'Compliance', (nonce) ->
      fd = new FormData()
      fd.append('username', $("#login_name").text())
      fd.append('nonce', nonce)
      fd.append('file', form.find('input[name=file]')[0].files[0])
      fd.append('file', form.find('input[name=file]')[1].files[0])
      fd.append('data', JSON.stringify(form.serializeObject()))
      $.ajax
        url: "#{location.protocol}//#{location.hostname}:8980/create_kyc_ticket",
        data: fd,
        processData: false,
        contentType: false,
        type: 'POST',
        success: (data) ->
            alert("Successfully saved:" + data)
        error: (err) ->
            alert("Error while saving:" + err)
            sputnik.log "Error:", err
        
sputnik.on "change_password_token", (args) ->
    $('#change_password_token_modal').modal "show"
sputnik.on "change_password_fail", (err) -> #BUG: this is not firing multiple times
    console.log "[mexbt:15 - hit error]"
    $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-danger').text("Error: #{err[1]}")

$("#change_password_token_button").click ->
    console.log "[mexbt:15 - hit!]"
    if $('#new_password_token').val() == $('#new_password_token_confirm').val()
        sputnik.changePasswordToken($('#new_password_token').val())
    else
        $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-danger').text "Passwords do not match"


sputnik.on "change_password_success", ->
    $('#change_password_token_modal').find('input,a,label,button').slideUp()
    $('#change_password_token_modal .alert').removeClass('alert-info').addClass('alert-success').text('Password reset')
    setTimeout(
        ->
            $('#change_password_token_modal').modal "hide"
    ,
        5000)

