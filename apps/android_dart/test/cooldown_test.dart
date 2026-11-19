import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/domain/pin_cooldown.dart';

void main() {
  test(
    'elapsed-time lock survives reopening, reboot, clock rollback and expires once',
    () {
      final record = <String, dynamic>{};
      PinCooldown.arm(record, 100000, 3);
      expect(PinCooldown.normalize(record, 160000, 3), 240000);
      final reopened = Map<String, dynamic>.from(record);
      expect(PinCooldown.normalize(reopened, 5000, 4), 235000);
      expect(PinCooldown.normalize(reopened, 2000, 4), 235000);
      expect(PinCooldown.normalize(reopened, 237001, 4), 0);
      expect(reopened, {'attempts': 0});
    },
  );
}
