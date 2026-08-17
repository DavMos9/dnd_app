import 'package:flet/flet.dart';

import 'apk_installer_service.dart';

/// Punto d'ingresso dell'estensione, registrato da Flet a runtime.
///
/// Pattern identico a `flet_file_picker`/`flet_image_picker` (a loro volta
/// copiati da flet-audio-recorder): ApkInstaller non ha superficie visiva
/// propria, è un servizio invocabile che apre l'installer di sistema e ritorna.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "ApkInstaller":
        return ApkInstallerService(control: control);
      default:
        return null;
    }
  }
}
