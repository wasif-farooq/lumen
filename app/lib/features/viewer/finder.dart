import 'package:flutter/foundation.dart';

/// "Find in file": the views listen; the same words again means the next match.
class Finder extends ChangeNotifier {
  String query = '';
  int times = 0; // how often this query was asked in a row

  void find(String q) {
    times = q == query ? times + 1 : 0;
    query = q;
    notifyListeners();
  }
}
