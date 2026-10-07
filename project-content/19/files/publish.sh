dotnet publish --use-current-runtime --sc true /p:PublishSingleFile=true /p:PublishTrimmed=true -o publish
sleep 3
cp -u publish/mail_app ~/MailApp
