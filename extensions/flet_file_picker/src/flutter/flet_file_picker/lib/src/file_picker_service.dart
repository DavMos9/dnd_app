import 'package:file_picker/file_picker.dart';
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart' show debugPrint;

/// Implementazione nativa del controllo Python `FilePicker`.
///
/// Pattern di dispatch (`addInvokeMethodListener` / switch su `name` /
/// `removeInvokeMethodListener` in dispose) copiato 1:1 da
/// `ImagePickerService` (`flet_image_picker`, stesso progetto) — vedi il
/// commento di provenienza in `file_picker.py`. La restituzione di un `Map`
/// (nome file + byte) tramite il valore di ritorno di `_invokeMethod` segue
/// lo stesso canale MsgPack standard già usato da `ImagePickerService` per
/// restituire byte immagine grezzi — qui incapsulati in una mappa perché,
/// a differenza della foto (nome sempre irrilevante per il chiamante), qui
/// serve anche il nome file originale (per riconoscere `.dndchar` vs
/// `.dndworld` e per i messaggi di errore mostrati all'utente).
class FilePickerService extends FletService {
  FilePickerService({required super.control});

  @override
  void init() {
    super.init();
    debugPrint("FilePicker.init($hashCode)");
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("FilePicker.$name($args)");
    switch (name) {
      case "pick_file":
        final Map<dynamic, dynamic> a = args is Map ? args : {};
        final List<dynamic>? rawExt = a["allowed_extensions"] is List
            ? a["allowed_extensions"] as List
            : null;
        final List<String>? allowedExtensions =
            (rawExt != null && rawExt.isNotEmpty)
                ? rawExt.map((e) => e.toString()).toList()
                : null;

        final FilePickerResult? result = await FilePicker.platform.pickFiles(
          type: allowedExtensions != null ? FileType.custom : FileType.any,
          allowedExtensions: allowedExtensions,
          withData: true,
        );

        if (result == null || result.files.isEmpty) {
          // Utente ha annullato la selezione — nessun errore, il lato
          // Python riceve None (vedi file_picker.py::pick_file).
          return null;
        }

        final PlatformFile picked = result.files.single;
        if (picked.bytes == null) {
          throw Exception(
              "file_picker non ha restituito i byte per ${picked.name}");
        }

        return {"name": picked.name, "bytes": picked.bytes};
      default:
        throw Exception("Unknown FilePicker method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("FilePicker(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
