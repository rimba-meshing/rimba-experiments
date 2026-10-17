# Ubuntu's OpenVDB development package lacks a CMake discovery module.
find_path(OpenVDB_INCLUDE_DIR NAMES openvdb/openvdb.h)
find_library(OpenVDB_LIBRARY NAMES openvdb)
include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(OpenVDB REQUIRED_VARS OpenVDB_LIBRARY OpenVDB_INCLUDE_DIR)
if(OpenVDB_FOUND AND NOT TARGET OpenVDB::openvdb)
  find_package(TBB REQUIRED CONFIG)
  find_package(Boost REQUIRED COMPONENTS iostreams)
  add_library(OpenVDB::openvdb UNKNOWN IMPORTED)
  set_target_properties(OpenVDB::openvdb PROPERTIES
    IMPORTED_LOCATION "${OpenVDB_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${OpenVDB_INCLUDE_DIR}"
    INTERFACE_LINK_LIBRARIES "TBB::tbb;Boost::iostreams")
endif()
