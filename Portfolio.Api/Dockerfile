FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Portfolio.Api/ ./
RUN dotnet publish Portfolio.Api.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
EXPOSE 443
# Les certificats sont montés au lancement (volume ./certs:/https), jamais copiés dans l'image
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "Portfolio.Api.dll"]
