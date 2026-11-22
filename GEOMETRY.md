# HMD-relative placement and named contours (0.24.0)

`pad_alignment.py` composes the support frame from the HMD pose and four local
values (Y distance, Z height, X tilt, Z rotation). The pivot is at local
(0,0,132) for the forehead and (0,0,78) for the closed support. Its local X
coordinate remains zero, even for a tilted/rotated HMD. Relative Y rotation is
zero. Old absolute support poses are decomposed once; their lateral offset and
independent Y rotation are discarded to enforce the requested centring.

`cushion_presets.py` selects Custom or the scan-derived VR Panda contour in
`vr_panda_198x48.json`. Tracing is smoothed, deskewed and independently calibrated
to the handwritten 198 and 48 mm dimensions. Contour points form the surface
boundary; triangulation excludes triangles outside the traced polygon. Radius
wraps its flat horizontal coordinate without replacing its silhouette.

Closed radius adjustment rebends the original reference around its 90 mm
reference cylinder, preserving its per-point radial residual and Z routing.
At 90 mm the original reference is returned unchanged. Existing bounded fitting
and construction checks remain; fitting-quality improvement is deferred.

# Forehead support and upper shell (0.23.0)

`forehead.py` owns the independent open base, capsule reference and assembly.
Capsule edges are subdivided in the flat plane before cylindrical wrapping;
long straight triangle chords must not cross the curved support. Dimensions
are stored in `.padfit` parameters with solver `forehead`. The common bounded
fitter accepts explicit reference data without replacing its closed reference.
The manual support pose is locked except optional world-Y refinement.

The upper-shell Bezier surface runs from the open base's top rear edge into
the fitted backing, with a vertical tangent at the backing and 2.5 mm nominal
wall. The contact guard trims new shell material. A support inside that guard
is rejected. Boolean union must be a single volume, and all support vertices
and face centres must remain on the final glue surface within 0.02 mm.
Print-frame and float-safe export checks are shared with the closed workflow.
These checks do not establish strength, comfort or USB cable compatibility.

# Contour pocket fill 01 (0.21.0)

The nose arch is the approved restart 06, including the 0.20.1 profile-height
correction for shifted placements. Pocket construction consumes its current
inner skin and the actual shell/pad surfaces in the magnetic base frame.
The roof joins the inner rear adapter rim to the unchanged nose/pad rim.
A quintic spatial fade tapers the fill into the side shell. Exact coincident
vertices are welded; opposite coincident faces are removed. A nose-wall guard
and the existing assembly guards protect the opening, adhesive face, HMD
contact envelope and magnet pockets. No cached user geometry is bundled.

The new fill can be disabled independently of the nose arch. Both options are
stored in project parameters. Exports keep the 0.20.2 rigid print-frame transform.

The sections below document earlier development stages and are historical.

# Remove rib-side rails (0.19.1)

Extend crown trimming beyond the coarse square-rib shoulder. The crown joins
the nominal root at +/-3 mm; outside it, trim to the existing wall instead
of leaving a raised rail. Preserve the original wall solid underneath the
trimming so no wall surface is cut. R3.25 crown, nominal 6 mm rib foot width,
source interfaces and longitudinal connections remain unchanged.

# Fully rounded rib crown (0.19.0)

The upper surface of each internal rib is one circular arc without a flat
strip. R = 3.25 mm preserves the existing 6 mm foot width and 2.5 mm overall
height with an uncut lower 0.5 mm rib root. Each half uses 24 arc segments.
Material is removed only from the rib crown, before the untouched base and
cushion are unioned. No new feet, end taper or shell deformation is introduced.

The earlier R1 fillet notes below are superseded by the fully rounded crown.

# Upper rib-edge fillets (0.19.0)

Keep the accepted 0.18.1 shell, five square rib roots and complete source
interfaces. Subtract only the upper two corner bands from each rib with a
1 mm quarter-circle profile, sampled at 12 arc segments. The flat centre,
lower 1.5 mm of rib height and longitudinal end routing stay unchanged.
Cutters affect only the shell additive solid; the magnetic base and cushion
are separately unioned unchanged afterwards. The existing trimmed-rib
connectivity and source-interface checks still apply.

Earlier development notes follow.

Only five internal ribs remain: three above and two below. The two side ribs are omitted.

# Continuous inward shell offset (0.18.0)

Fix the crossed inner/outer skin introduced by 0.17.0's independent inner
longitudinal loft. Both wall and square ribs now offset inward along the same
outer-skin normal throughout. The signed inward offset must remain at least
1.49 mm before assembly. Exact adhesive-side guards trim end excess; every
trimmed rib must remain connected to the unchanged base and cushion backing.

The outer temple extension uses a single smooth cubic transition instead of
a short flared shoulder. The narrow guide still controls the main wall; the
rear end reaches the actual pad backing. Stand 16 remains the base asset.
The earlier independent loft description below is obsolete.

# Narrow wall with rear join (0.17.0)

The approved outer base connection and Stand 16 asset remain unchanged.
The main temple wall keeps the narrow lateral guide from 0.16.0. Only in the
last 20 mm of longitudinal travel does it flare toward the rear pad rim
(approximately 1 mm template rim). The extension is confined to the temple
sector; the central forehead and lower attachment routes stay at their old
positions. This is a visual design variant for user review.

Square inward ribs remain integral to the shell. After the adhesive, mating
and magnet clearances are applied, every rib is independently checked for a
single connected positive solid, overlap with both unchanged source bodies,
and retention inside the final print body. Raw spine points can lie inside
intentionally removed adhesive-side material, so they are superseded by this
complete trimmed-rib test.

Earlier development notes follow.

# Shell correction (0.16.0)

The approved outer base connection is retained. The pad attachment returns to
its earlier lateral route; temple extension changes only the longitudinal
base Y coordinate of the connecting skin, never its lateral coordinates.
Reinforcements are inward flat-topped, square-edged ribs without end fading.
Their inner end sections follow the actual backing surface and overlap the
pad, rather than relying on rounded connection patches. Stand 16 and its
magnet pockets remain unchanged. Nasal baffle stays disabled.

The following notes describe previous stages.

# Current shell (0.15.0)

The magnetic base is the physically approved Stand 16 asset, copied without
changes. Its rear cap supplies the shell attachment at the outer boundary
(0.005 mm numerical inset). The shell starts parallel to the outer base wall
and curves toward the cushion backing. At the temples the attachment moves
toward a 1 mm rim in the cushion template; forehead and lower centre routing
remain at their prior positions.

The shell uses a smooth outer skin with 1.5 mm inward thickness. Seven rounded
reinforcements are additional inward thickness of that same skin, not separate
feet or patches. They taper into the backing wall near the adhesive interface.
The nasal baffle remains disabled. Geometry checks cover a connected print
solid, source mating and adhesive surfaces, free magnets and rib connectivity.
The user's visual review and next physical fit test remain necessary.

The sections below describe earlier development stages.

# Probe 06 assembly (0.7 beta)

The source V2 model is intersected with a closed contour-depth cutter 12 mm
behind the original front profile. All original source vertices and face
centroids in the protected front 8 mm were checked against the extracted band
(maximum deviation 3.4e-11 mm). Only the new rear cut is capped. The asset contains
no head scan. Shape, magnet pockets and forward engagement surfaces are not
resized. This is a new separate base, without the original rear nose/vent and
headband extensions.

Seven short strips are sampled barycentrically on the actual backing mesh, with
feet partly embedded into its thickness. Convex solid bridges connect these feet
to ports on the rear cut of the source base. Manifold3D Mesh64 unions them with
the support and base. Each bridge must overlap both components; output must be
one positive-volume, closed, consistently oriented component. Invalid joins and
excessive separation are rejected rather than moving either part automatically.

A Boolean envelope test rejects material added within the protected front band
(volume tolerance 1e-5 mm3). Every protected base vertex is checked, plus 2000
surface samples. All adhesive vertices and triangle centroids must remain on
the final exterior within 1e-5 mm. This verifies the preserved interfaces,
not structural strength, exact continuous gap or printer accuracy. Mesh topology
and both export formats are regression tested. Optical/HMD registration and
mechanical strength are explicitly unverified in the report.

The independent base pose is persisted with the cushion parameters. Updating
it invalidates only the assembly, preserving the user's cushion/eye alignment.
Changing the head or cushion invalidates both. Import and head rotations stay
on the current step; project opening alone may advance to positioning.

# Reference-based fitting (0.6 beta)

`referencefit.py` replaces the default 0.5 free face projection. Bundled
`vrcover_probe04.npz` contains only the confirmed support contact/solid surface,
UV parameterisation and topology, without a head scan or the full V2 gasket.

Thirty smooth, broad XY controls deform the confirmed surface. Local Z is
unchanged. Alternating closest-surface queries and bounded least squares fit
the desired foam plus hook-and-loop gap, with penalties for metric changes,
compressed-foam limits and large control values. From 0.6.1, optional refinement is off by default and only allows Y translation
within 20 mm. X, Z and every rotation remain exactly as manually requested,
even when loading an older project with refinement enabled. This is not optical registration or landmark detection.

A final line search enforces at most 4% change on every unique contact edge and
the selected maximum displacement. The baseline is the confirmed curved Probe
04, not the UV chart or a projected flat silhouette. Fixed UV charts must not be
mistaken for an isometric unwrapped cushion measurement. Limiting edge strain
and preserving Z routing do not prove leather compatibility; physical tests
remain necessary.

All contact vertices and face centroids are tested against actual head triangles.
Signed gaps use the backing's outward direction; they are sampled local clearance
estimates, not a volumetric signed-distance proof. Nearest faces touching open
scan rims are rejected rather than treated as valid measured coverage. Gaps
below 1 mm are rejected; gaps outside 3.5-10 mm plus hook-and-loop require review.
Normals from a smooth UV surface produce a nominal 1.5 mm offset. Checks cover
closed topology, winding, positive volume, collapsed triangles, reference/offset
face orientation and sampled minimum layer distance of at least 1.45 mm.
This is not an exhaustive self-intersection or continuous thickness proof.

Reports include extrema/percentiles of gaps, metric change, maximum displacement,
unchanged local Z, comparison with the undeformed surface at the same final pose,
settings and reference fingerprint. Pressure, stiffness and optics are explicitly
marked unverified. Exports translate rigidly to minimum Z = 0 without scaling;
head scan coordinates remain in project data. Projects save the original requested
pose for deterministic replay instead of repeatedly refining the previous result.

# Previous 0.5 algorithm (retained for regression tests, not default)

# Cushion-first geometry (0.5 beta)

The default design starts from the user-approved 236 x 116 mm VRcover outline,
not from the V2 gasket. The exact accepted JSON coordinates are bundled as a
separate immutable source. A conforming triangulation preserves its U-shaped
opening and original boundary; internal Delaunay edge flips improve mesh
quality without changing boundary segments.

Radial rays in an explicitly positioned cylindrical frame find the first actual
head triangle for every support vertex. Thin-plate radial smoothing is bounded
by the chosen radial tolerance. Horizontal arc-length reparameterisation and
surface-constrained cloth relaxation reduce deviation from the flat metric.
A parameter-space orientation barrier prevents local cloth folds. After
relaxation, the new locations are ray-checked again against actual scan data.
Missing coverage is rejected, including on incomplete scans. No holes are filled.

The smoothed contact layer is offset outward to the requested effective foam
clearance, with a small reserve and global radial correction as needed. Checks
sample all contact vertices and triangle centroids against the source triangles.
The maximum gap remains visible rather than being hidden as an average.

Differential normals of the smooth surface produce the nominal 1.5 mm backing
layer. Checks cover closed topology, winding, collapsed triangles, offset face
orientation and sampled distance to the backing layer (minimum 85 percent of
nominal thickness). This is not an exhaustive solid self-intersection or exact
continuous minimum wall-thickness proof. Foam compression and physical fit need
a test piece.

All unique surface edges at least 1 mm long are compared with the original flat
metric. The report includes minimum/maximum strain and the 95th percentile of
absolute strain. Warnings flag P95 > 8 percent or worst strain > 15 percent;
local strain above 50 percent is rejected. These are provisional engineering
review thresholds, not a measured material limit for VRcover foam. Gap warnings
flag a maximum clearance above padding + smoothing allowance + 0.75 mm.
Warnings block export until the user reviews them as a test piece.

The magnetic adapter, nose section, headband attachment, ventilation and final
connecting shell are not generated in this stage. No HMD alignment is inferred.

# Legacy PFDMR V2 restricted-contact profile (0.4 beta)

## Correction of version 0.3

The previous broad deformation band changed too much of the V2. Its approximate HMD registration was incorrect and has been withdrawn. Version 0.4 does not display or reuse it as a valid docking reference. HMD data embedded in old projects is retained as raw data, with docking explicitly invalid. Broad version-0.3 results cannot enable export in the new app; the original meshes and pose remain readable.

## Mandatory protected features

Supported source: Pfd 108Fov Face Gasket mod V2 by Sir Dominik, identified by geometry hash. The original V2 remains the base; no parts are replaced from the original PFDM gasket.

The upper extra-headband attachment, complete nose opening and associated ventilation assembly must stay unchanged. The known V2 uses deliberately generous fixed feature regions in the established fitting frame:

- Upper attachment: absolute X at most 36 mm, height at least 96 mm.
- Nose/vent assembly: absolute X at most 55 mm, height at most 82 mm.

These guards apply through the entire depth of the model, with a transition outside the fixed regions. They cannot be unlocked by the UI, brush, strip-width control or solver. The complete front mounting band also stays fixed. A conservative mask includes extra surrounding material to avoid deforming structural roots. Its visible footprint must be checked against the actual model.

## Approved rear contact strip

Default width: 6 mm from the existing rear contact envelope; configurable from 2 to 12 mm. Material farther forward stays fixed. Changing the width or protection marks invalidates the result and clears the user's region confirmation. Before calculating, inspect the original with the region overlay and confirm the orange editable area.

Purple shows the permanently protected attachment/nose features, blue other fixed material, orange the editable strip. Shift + click with the protection brush adds a source-frame protection sphere. It can only remove material from the editable region; it cannot unlock mandatory guards. Undo removes the last user-added mark, preserving all mandatory protection. Marks and width are embedded in project metadata and checked against the cached result on reopening.

## Local deformation

Long movable edges are subdivided conformingly. Every source vertex retains its position in the undeformed reference; original triangles wholly in fixed material are retained. No ventilation cuts are filled.

A positive graph Laplacian solves harmonic displacement only for approved vertices. All protected vertices have exactly zero displacement as Dirichlet constraints. Targets are projected to the actual head triangles at the requested padding clearance with a small reserve. Harmonic displacement avoids the global extrapolation and overshoot of the former broad RBF field.

Quality checks cover oriented surface triangles, limited local corrections, collapsed triangles, boundary and nonmanifold edges, exact protected coordinates and signed clearance at the sampled movable contact lip. They are surface checks, not a claim of a volumetric Jacobian or exhaustive self-intersection/wall-thickness validation. If the approved strip cannot accommodate the requested fit, calculation is rejected. It never broadens the editable region automatically.

The nose and protected attachment are not fitted to the head. Their original gaps may remain. Reports distinguish protected regions from fitted regions. Physical fit and foam compression still need a test print.

## Persistence and export

Project format 2 remains readable. Results require the current profile ID, exactly matching region settings, deterministic refined reference, fixed coordinates, pose and padding. Head, gasket, brush settings and old raw HMD data stay local. Gasket STL/3MF exports never include the head or HMD. Original fixed STL float32 values remain exact; 3MF uses 17 significant digits.

## View and settings

Recenter changes camera centre and zoom only, using visible model bounds, viewport aspect ratio and field of view. It never resets the alignment. Hidden head/HMD geometry is excluded. Settings has separate Language and Updates menu entries, each opening its own page.
