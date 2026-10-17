"""Timer and allocation categories shared with the manuscript analysis.

Nested and enclosing timer scopes must never be added together.
"""

PERSISTENT_DEVICE_FIELDS = {
    "accumulated_vertices_global",
    "accumulated_faces_global",
}


ACCUMULATED_DEPTH_DEVICE_FIELDS = {
    "accumulated_depth",
    "projected_rows",
    "projected_cols",
    "projected_ranges",
    "large_face_indices",
    "active_face_ranges",
    "active_vertex_ranges",
}


BOUNDARY_DEVICE_FIELDS = {
    "current_vertex_normal_sums",
    "edge_keys",
    "oriented_boundary_edges",
    "boundary_edges",
}


RANGE_MESHING_DEVICE_FIELDS = {
    "current_vertices_local", "flags", "offsets",
    "points", "pixel_last_index", "valid", "clean_valid", "meshing_valid",
    "new_vertex_allowed", "final_new_allowed", "ri_thin_input", "ri_thin_eroded",
    "ri_thin_grown", "ri_thin_removed", "stitch_connection_mask",
    "stitch_connection_old_support", "stitch_connection_new_support",
    "stitch_connection_next_frontier", "pixel_xyz", "scan_ranges", "filled_ranges",
    "fill_scratch_ranges", "fill_support_ranges", "fill_anchor", "fill_scratch_anchor",
    "compacted_current_vertices", "filled_pixel_xyz", "current_vertex_rows",
    "current_vertex_cols", "current_vertex_ranges", "filled_vim", "macro_quads",
    "macro_quad_count", "macro_candidate_flags", "macro_selected_size",
    "macro_next_size", "face_records", "face_record_count", "face_overflow",
    "quad_face_flags", "faces",
}


def stage_categories() -> dict[str, set[str]]:
    """Non-overlapping elapsed timer scopes for the four method stages.

    Never sum a host aggregate with its nested diagnostics. Untimed work and
    unselected scopes remain in the end-to-end residual, not a pure GPU/CPU bin.
    """
    return {
        "stage_a": {
            "accum.prepare_buffers", "accum.clear_depth",
            "accum.transform_and_project_vertices", "accum.mark_large_faces",
            "accum.large_face_prefix_sum", "accum.rasterize_small_faces",
            "accum.compact_large_faces", "accum.rasterize_large_faces",
            "scan.allocate_and_upload", "scan.project_points",
            "scan.materialize_pixels", "scan.filter_small_range_components",
        },
        "stage_b": {
            "scan.materialize_ranges", "scan.prepare_meshing_valid",
            "scan.prepare_meshing_ranges", "scan.prepare_accumulated_fill_support",
            "scan.merge_accumulated_fill_support", "scan.fill_irregular_ri",
            "scan.ranges_to_xyz", "scan.mark_new_vertex_allowed",
            "scan.filter_ri_thin_components", "scan.vertex_prefix_sum",
            "scan.build_vertices", "stitch.connection_mask",
        },
        "stage_c": {
            "mesh.mark_candidate_faces", "mesh.plan_macro_quads",
            "mesh.emit_macro_faces", "mesh.sort_face_keys", "mesh.unique_prefix_sum",
            "mesh.compact_faces", "mesh.filter_isolated_components",
        },
        "stage_d": {
            "stitch.extract_new_boundary", "stitch.synchronize_stitch_inputs.total",
            "stitch.compact_input", "stitch.core_v0",
            "stitch.update_host_boundary_combined", "stitch.update_host_boundary_pending",
            "stitch.hole_fill.total_host", "stitch.append_faces",
        },
    }


def device_memory_group(field: str) -> str:
    groups = {
        "gpu_mesh": PERSISTENT_DEVICE_FIELDS,
        "gpu_accumulated_depth": ACCUMULATED_DEPTH_DEVICE_FIELDS,
        "gpu_range_meshing": RANGE_MESHING_DEVICE_FIELDS,
        "gpu_boundary": BOUNDARY_DEVICE_FIELDS,
    }
    matches = [name for name, fields in groups.items() if field in fields]
    if len(matches) != 1:
        raise ValueError(f"CUDA field needs one audited memory category: {field}")
    return matches[0]
