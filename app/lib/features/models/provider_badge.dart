import 'package:flutter/material.dart';

import '../../shared/theme.dart';

/// "Local" or "Cloud", with what that means in the tooltip.
class ProviderBadge extends StatelessWidget {
  const ProviderBadge({super.key, required this.cloud});
  final bool cloud;
  @override
  Widget build(BuildContext context) => Tooltip(
        message: cloud ? 'File contents and images are sent to this service' : 'Runs on this laptop or your local network',
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(color: (cloud ? C.accent : C.green).withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(cloud ? Icons.cloud_outlined : Icons.lock_outline, size: 12, color: cloud ? C.accent : C.green),
            const SizedBox(width: 4),
            Text(cloud ? 'Cloud' : 'Local', style: TextStyle(fontSize: 12, color: cloud ? C.accent : C.green, fontWeight: FontWeight.w500)),
          ]),
        ),
      );
}
