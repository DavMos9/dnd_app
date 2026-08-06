import 'dart:io';
import 'dart:typed_data';

import 'package:flet/flet.dart';
import 'package:image_picker/image_picker.dart';

/// Implementazione nativa del controllo Python `ImagePicker`.
///
/// Pattern di dispatch (`addInvokeMethodListener` / switch su `name` /
/// `removeInvokeMethodListener` in dispose) copiato 1:1 da
/// `AudioRecorderService` (flet-audio-recorder, pacchetto ufficiale Flet) —
/// vedi il commento di provenienza in `image_picker.py`. La restituzione dei
/// byte immagine tramite il valore di ritorno di `_invokeMethod` (canale
/// MsgPack standard, non `DataChannel`) segue invece il precedente reale di
/// `CameraControl._invokeMethod` -> case "take_picture" in flet-camera, che
/// fa esattamente questo con foto a piena risoluzione.
class ImagePickerService extends FletService {
  ImagePickerService({required super.control});

  final ImagePicker _picker = ImagePicker();

  @override
  void init() {
    super.init();
    debugPrint("ImagePicker.init($hashCode)");
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("ImagePicker.$name($args)");
    switch (name) {
      case "pick_image":
        final Map<dynamic, dynamic> a = args is Map ? args : {};
        final int? imageQuality = parseInt(a["image_quality"]);
        final double? maxWidth = parseDouble(a["max_width"]);
        final double? maxHeight = parseDouble(a["max_height"]);

        final XFile? picked = await _picker.pickImage(
          source: ImageSource.gallery,
          imageQuality: imageQuality,
          maxWidth: maxWidth,
          maxHeight: maxHeight,
        );

        if (picked == null) {
          // Utente ha annullato la selezione — nessun errore, il lato
          // Python riceve None (vedi image_picker.py::pick_image).
          return null;
        }

        final Uint8List bytes = await File(picked.path).readAsBytes();
        return bytes;
      default:
        throw Exception("Unknown ImagePicker method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("ImagePicker(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
