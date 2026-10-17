# Ubuntu's OpenVDB development package lacks a CMake discovery module.
find_path(OpenVDB_INCLUDE_DIR NAMES openvdb/openvdb.h)
find_library(OpenVDB_LIBRARY NAMES openvdb)
include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(OpenVDB REQUIRED_VARS OpenVDB_LIBRARY OpenVDB_INCLUDE_DIR)
if(OpenVDB_FOUND AND NOT TARGET OpenVDB::openvdb)
  # OpenVDB 8.1 links classic TBB, while Ubuntu's dev dependency supplies oneTBB.
  # Keep the matching classic headers separate from the system development files.
  find_path(TBB_INCLUDE_DIR NAMES tbb/tbb.h PATHS "${TBB_ROOT}/include" NO_DEFAULT_PATH REQUIRED)
  find_library(TBB_LIBRARY NAMES libtbb.so.2 REQUIRED)
  find_package(Boost REQUIRED COMPONENTS iostreams)
  add_library(OpenVDB::openvdb UNKNOWN IMPORTED)
  set_target_properties(OpenVDB::openvdb PROPERTIES
    IMPORTED_LOCATION "${OpenVDB_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${OpenVDB_INCLUDE_DIR};${TBB_INCLUDE_DIR}"
    INTERFACE_LINK_LIBRARIES "${TBB_LIBRARY};Boost::iostreams")
endif()
