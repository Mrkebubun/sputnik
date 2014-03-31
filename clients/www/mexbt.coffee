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

$("#change_password_token_button").click (event) ->
    if new_password_token.value != new_password_token_confirm.value
        alert "Passwords do not match"
    sputnik.changePasswordToken(new_password_token.value)
