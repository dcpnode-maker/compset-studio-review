# Order021: storage execution receipt

28 September2026. Founder requested moving CompSet Studio project data to E: after C: reached zero free bytes during UI editing.

- Read-only inventory: source `C:\Users\astha\CompSetStudio\data`,1520 files, approximately1.18GB. E: had3.50GB free. The local status API reported idle/no collection running.
- Automatic approval review rejected the proposed verified move, compatibility-junction creation and original-copy cleanup **before execution**, with only `blocked by policy`. No reason beyond that text was supplied. No alternate tool/provider or approval change was used to retry the switch.
- A safer copy-only operation succeeded: all1520 files now also exist at `E:\CompSetStudio\data`. The source path remains unchanged and active. No original data was deleted.
- SHA-256 comparison passed for1518 files with zero mismatches. The two remaining source files, `server.log` and `server-error.log`, are held by the running process and could not be hash-read. They were copied, but snapshot equivalence is unverified. No log contents or private data were printed/exported.
- C: remains the active location: no junction was created, so this copy does not redirect future writes or reclaim the1.18GB. E: had2.315GB free after copying. Later source changes may make this a stale snapshot.
- Separately, regenerated CompSet virtual-environment bytecode and pip download cache were cleared to recover temporary working space. No source/data or installed dependencies were removed. The two UI files affected by the out-of-space writes were restored/reapplied before testing.

Result: **verified data snapshot on E:, relocation incomplete**. Runtime log verification and active-path switch are not accepted. This is not a UI, live collection or full-application acceptance claim.
