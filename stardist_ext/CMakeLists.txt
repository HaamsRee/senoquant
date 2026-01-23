cmake_minimum_required(VERSION 3.18)
project(senoquant_stardist_ext LANGUAGES C CXX)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module NumPy)

set(STARDIST_LIB_DIR "${CMAKE_CURRENT_LIST_DIR}/../src/senoquant/tabs/segmentation/stardist_onnx_utils/_stardist/lib")

set(STARDIST_EXTERNAL_DIR "${STARDIST_LIB_DIR}/external")
set(STARDIST_QHULL_DIR "${STARDIST_EXTERNAL_DIR}/qhull_src/src")

file(GLOB QHULL_C_SOURCES "${STARDIST_QHULL_DIR}/libqhull_r/*.c")
file(GLOB QHULL_CPP_SOURCES "${STARDIST_QHULL_DIR}/libqhullcpp/*.cpp")

set(STARDIST_2D_SOURCES
    "${STARDIST_LIB_DIR}/stardist2d.cpp"
    "${STARDIST_LIB_DIR}/utils.cpp"
    "${STARDIST_EXTERNAL_DIR}/clipper/clipper.cpp"
)

set(STARDIST_3D_SOURCES
    "${STARDIST_LIB_DIR}/stardist3d.cpp"
    "${STARDIST_LIB_DIR}/stardist3d_impl.cpp"
    "${STARDIST_LIB_DIR}/stardist3d_lib.c"
    "${STARDIST_LIB_DIR}/utils.cpp"
    ${QHULL_C_SOURCES}
    ${QHULL_CPP_SOURCES}
)

set_source_files_properties(
    "${STARDIST_LIB_DIR}/stardist3d_lib.c"
    PROPERTIES LANGUAGE CXX
)

add_library(stardist2d MODULE ${STARDIST_2D_SOURCES})
add_library(stardist3d MODULE ${STARDIST_3D_SOURCES})

set_target_properties(stardist2d PROPERTIES PREFIX "")
set_target_properties(stardist3d PROPERTIES PREFIX "")

if(Python3_EXTENSION_SUFFIX)
    set_target_properties(stardist2d PROPERTIES SUFFIX "${Python3_EXTENSION_SUFFIX}")
    set_target_properties(stardist3d PROPERTIES SUFFIX "${Python3_EXTENSION_SUFFIX}")
endif()

target_include_directories(stardist2d PRIVATE
    "${STARDIST_LIB_DIR}"
    "${STARDIST_EXTERNAL_DIR}/clipper"
    "${STARDIST_EXTERNAL_DIR}/nanoflann"
    "${Python3_INCLUDE_DIRS}"
    "${Python3_NumPy_INCLUDE_DIRS}"
)

target_include_directories(stardist3d PRIVATE
    "${STARDIST_LIB_DIR}"
    "${STARDIST_EXTERNAL_DIR}/nanoflann"
    "${STARDIST_QHULL_DIR}"
    "${Python3_INCLUDE_DIRS}"
    "${Python3_NumPy_INCLUDE_DIRS}"
)

target_compile_definitions(stardist2d PRIVATE NPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION)
target_compile_definitions(stardist3d PRIVATE NPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION)
target_compile_options(stardist3d PRIVATE $<$<COMPILE_LANGUAGE:C>:-include;stdbool.h>)

target_link_libraries(stardist2d PRIVATE Python3::Module)
target_link_libraries(stardist3d PRIVATE Python3::Module)

find_package(OpenMP)
# MSVC rejects unsigned OpenMP loop indices (C3016) in upstream StarDist code.
# Disable OpenMP on MSVC to avoid patching vendored sources.
if(OpenMP_CXX_FOUND AND NOT APPLE AND NOT MSVC)
    target_link_libraries(stardist2d PRIVATE OpenMP::OpenMP_CXX)
    target_link_libraries(stardist3d PRIVATE OpenMP::OpenMP_CXX)
endif()

set(INSTALL_SUBDIR "senoquant/tabs/segmentation/stardist_onnx_utils/_stardist/lib")

install(TARGETS stardist2d stardist3d
    LIBRARY DESTINATION "${INSTALL_SUBDIR}"
)
