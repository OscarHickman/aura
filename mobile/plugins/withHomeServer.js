const { withAndroidManifest, withGradleProperties, AndroidConfig } = require('expo/config-plugins');

// Server addresses are chosen at runtime, including HTTP LAN/Tailscale hosts.
// Expo Go permits these connections, but release manifests must opt in too.
module.exports = config => {
  config = withAndroidManifest(config, config => {
    const application = AndroidConfig.Manifest.getMainApplicationOrThrow(config.modResults);
    application.$['android:usesCleartextTraffic'] = 'true';
    return config;
  });

  config = withGradleProperties(config, config => {
    AndroidConfig.BuildProperties.updateAndroidBuildProperty(config.modResults, 'android.compileSdkVersion', '36');
    AndroidConfig.BuildProperties.updateAndroidBuildProperty(config.modResults, 'android.targetSdkVersion', '36');
    AndroidConfig.BuildProperties.updateAndroidBuildProperty(config.modResults, 'android.buildToolsVersion', '36.0.0');
    return config;
  });

  return config;
};

