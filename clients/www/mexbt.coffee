@compliance_client_handler = (form) ->
  console.log "[mexbt:2 - form]", form
  fd = new FormData(form)
  $.ajax
    url: 'script.php',
    data: fd,
    processData: false,
    contentType: false,
    type: 'POST',
    success: (data) -> alert(data)
        
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
    success: (data) -> alert(data)

$ ->
  $('#chatBox').keypress (e)-> $('#chatButton').click() if e.keyCode == 13