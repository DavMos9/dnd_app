import 'package:flet/flet.dart';

import 'file_picker_service.dart';

/// Punto d'ingresso dell'estensione, registrato da Flet a runtime.
///
/// Pattern identico a `flet_image_picker`/Extension (a sua volta copiato da
/// flet-audio-recorder): FilePicker non ha superficie visiva propria, è un
/// servizio invocabile una tantum che apre il selettore di sistema e ritorna.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FilePicker":
        return FilePickerService(control: control);
      default:
        return null;
    }
  }
}
