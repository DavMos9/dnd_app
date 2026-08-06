import 'package:flet/flet.dart';

import 'image_picker_service.dart';

/// Punto d'ingresso dell'estensione, registrato da Flet a runtime.
///
/// Pattern identico a quello reale di flet-audio-recorder
/// (`FletService createService`, non `createWidget`): ImagePicker non ha
/// una superficie visiva propria (a differenza di flet-camera, che deve
/// mostrare l'anteprima live) — è un servizio invocabile una tantum, che
/// apre il selettore di sistema e ritorna.
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "ImagePicker":
        return ImagePickerService(control: control);
      default:
        return null;
    }
  }
}
