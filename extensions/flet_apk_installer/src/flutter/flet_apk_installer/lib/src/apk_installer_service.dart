import 'dart:io' show Platform;

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart' show debugPrint;
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

/// Implementazione nativa del controllo Python `ApkInstaller`.
///
/// Pattern di dispatch (`addInvokeMethodListener` / switch su `name` /
/// `removeInvokeMethodListener` in dispose) copiato 1:1 da
/// `FilePickerService` (`flet_file_picker`, stesso progetto).
///
/// Tre metodi, uno solo indispensabile:
///   - `install`      → apre la finestra di installazione di sistema;
///   - `download_dir` → la cartella che il FileProvider di open_filex sa
///                      esporre (diagnostica: è il punto più probabile di
///                      rottura, vedi il commento sotto);
///   - `can_install`  → informativo, per messaggi più chiari lato Python.
class ApkInstallerService extends FletService {
  ApkInstallerService({required super.control});

  /// MIME type degli APK. Deve essere ESATTO: con un MIME generico
  /// (`application/octet-stream`) Android aprirebbe un selettore di
  /// applicazioni invece dell'installer di pacchetti.
  static const String _apkMimeType = "application/vnd.android.package-archive";

  @override
  void init() {
    super.init();
    debugPrint("ApkInstaller.init($hashCode)");
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("ApkInstaller.$name($args)");
    switch (name) {
      case "install":
        final Map<dynamic, dynamic> a = args is Map ? args : {};
        final String apkPath = (a["apk_path"] ?? "").toString();
        if (apkPath.isEmpty) {
          throw Exception("apk_path mancante");
        }
        if (!Platform.isAndroid) {
          // Su desktop/iOS non esiste alcun installer di pacchetti da aprire:
          // dirlo, invece di fallire in modo oscuro. Il lato Python non arriva
          // mai qui (controlla `page.platform`), ma l'estensione non deve
          // dipendere da quel controllo per essere corretta.
          throw Exception(
              "l'installazione di un APK è possibile solo su Android");
        }

        // OpenFilex genera l'URI `content://` tramite il FileProvider che il
        // pacchetto dichiara nel PROPRIO AndroidManifest.xml, unito al nostro
        // dal manifest merger di Gradle. È il motivo per cui questa estensione
        // non contiene una riga di Kotlin.
        final OpenResult result = await OpenFilex.open(
          apkPath,
          type: _apkMimeType,
        );

        debugPrint(
            "ApkInstaller.install → ${result.type} / ${result.message}");
        if (result.type != ResultType.done) {
          // Il messaggio torna al lato Python, che lo mostra all'utente insieme
          // al percorso del file già scaricato: meglio un errore leggibile che
          // un pulsante che sembra non fare nulla.
          throw Exception(
              "apertura dell'installer non riuscita (${result.type}): "
              "${result.message}");
        }
        return result.message;

      case "download_dir":
        if (!Platform.isAndroid) {
          return null;
        }
        // getExternalStorageDirectory() = getExternalFilesDir(null) su Android:
        // l'albero che i provider_paths di open_filex espongono.
        //
        // ⚠️ QUESTA È L'ASSUNZIONE PIÙ FRAGILE DELL'INTERA ESTENSIONE, e non è
        // verificabile senza un dispositivo reale: se i provider_paths di
        // open_filex NON coprono questo albero, `install` fallisce con un errore
        // di permessi sull'URI. Il rimedio, in quel caso, è scaricare l'APK qui
        // invece che nella cartella privata dell'app — e cambia una riga sul
        // lato Python (`data/database.py::get_updates_path`), non il disegno.
        final dir = await getExternalStorageDirectory();
        return dir?.path;

      case "can_install":
        if (!Platform.isAndroid) {
          return false;
        }
        // `canRequestPackageInstalls()` non è esposto da alcun plugin Flutter
        // pubblicato: chiederlo richiederebbe il codice Kotlin che questa
        // estensione evita di proposito. Si restituisce `true`: `install()` va
        // tentata comunque, perché quando il permesso manca Android mostra da sé
        // la finestra "per la tua sicurezza…" con la scorciatoia alle
        // impostazioni. Il metodo resta nell'interfaccia per non doverla
        // cambiare se un giorno servisse davvero distinguere i due casi.
        return true;

      default:
        throw Exception("Unknown ApkInstaller method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("ApkInstaller(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
