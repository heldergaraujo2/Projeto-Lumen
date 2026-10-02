*** Begin Patch
*** Update File: app/evolution/autonomous_progress.py
@@
         self.save()
 
         if self.state.stagnation_steps >= self.stagnation_limit:
-            for candidate in ("describe_toolset", "observe_unreal", "unreal_call", "research", "evolve_code"):
-                if candidate in available and self.admit(candidate):
-                    self.state.stagnation_steps = 0
-                    self.save()
-                    return ProgressDecision(candidate, "stagnation guard forced a new capability step", True)
+            if (
+                "describe_toolset" in available
+                and any(item not in self.state.described_toolsets for item in self.state.known_toolsets)
+                and self.admit("describe_toolset")
+            ):
+                self.state.stagnation_steps = 0
+                self.save()
+                return ProgressDecision("describe_toolset", "stagnation guard forced a new capability step", True)
+            if "observe_unreal" in available and self.state.known_toolsets and ctx.get("can_observe") and self.admit("observe_unreal"):
+                self.state.stagnation_steps = 0
+                self.save()
+                return ProgressDecision("observe_unreal", "stagnation guard forced a new capability step", True)
+            if "unreal_call" in available and self.state.observations and ctx.get("can_unreal_call") and self.admit("unreal_call"):
+                self.state.stagnation_steps = 0
+                self.save()
+                return ProgressDecision("unreal_call", "stagnation guard forced a new capability step", True)
+            if "research" in available and ctx.get("can_research") and self.admit("research"):
+                self.state.stagnation_steps = 0
+                self.save()
+                return ProgressDecision("research", "stagnation guard forced a new capability step", True)
+            if "evolve_code" in available and ctx.get("can_evolve_code") and self.admit("evolve_code"):
+                self.state.stagnation_steps = 0
+                self.save()
+                return ProgressDecision("evolve_code", "stagnation guard forced a new capability step", True)
*** End Patch