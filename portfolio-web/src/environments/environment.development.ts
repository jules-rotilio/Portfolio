/**
 * Développement (ng serve) : URL relatives (/api/...), transmises à l'API locale par le proxy du serveur de dev
 * (ng serve --proxy-config proxy.conf.json). Le navigateur ne parle qu'à localhost:4200, donc pas de blocage CORS.
 */
export const environment = {
  apiOrigin: ''
};
