// Configuration Karma : identique à celle d'Angular par défaut, avec en plus un Chrome sans interface
// pour lancer les tests sur le serveur / en CI :  npm test -- --watch=false --browsers=ChromeHeadlessCI
// sans Chrome :  FIREFOX_BIN=/usr/bin/firefox-esr npm test -- --watch=false --browsers=FirefoxHeadless
module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-firefox-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    client: {
      jasmine: {},
      clearContext: false, // garde les résultats Jasmine visibles dans le navigateur
    },
    jasmineHtmlReporter: {
      suppressAll: true,
    },
    coverageReporter: {
      dir: require('path').join(__dirname, './coverage/portfolio-web'),
      subdir: '.',
      reporters: [{ type: 'html' }, { type: 'text-summary' }],
    },
    reporters: ['progress', 'kjhtml'],
    browsers: ['Chrome'],
    customLaunchers: {
      ChromeHeadlessCI: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox'], // nécessaire dans un conteneur Docker
      },
    },
    restartOnFileChange: true,
  });
};
