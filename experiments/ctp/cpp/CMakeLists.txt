cmake_minimum_required(VERSION 3.16)

project(derivatives_monitor_ctp_md LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "This target requires native Linux")
endif()

if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "The bundled CTP SDK requires Linux x86-64")
endif()

set(CTP_SDK_ROOT
    "${CMAKE_CURRENT_SOURCE_DIR}/../sdk/v6.7.13_20260225/linux64/mdapi"
    CACHE PATH "Path to the bundled CTP Linux market-data SDK")

set(CTP_MD_LIBRARY "${CTP_SDK_ROOT}/thostmduserapi_se.so")
set(CTP_MD_HEADER "${CTP_SDK_ROOT}/ThostFtdcMdApi.h")

if(NOT EXISTS "${CTP_MD_LIBRARY}" OR NOT EXISTS "${CTP_MD_HEADER}")
    message(FATAL_ERROR
        "CTP Linux market-data SDK is incomplete at ${CTP_SDK_ROOT}. "
        "The repository must contain the three CTP headers and thostmduserapi_se.so.")
endif()

find_package(Threads REQUIRED)

add_executable(ctp_md src/main.cpp)
target_compile_features(ctp_md PRIVATE cxx_std_17)
target_compile_options(ctp_md PRIVATE -Wall -Wextra -Wpedantic)
target_include_directories(ctp_md SYSTEM PRIVATE "${CTP_SDK_ROOT}")
target_link_directories(ctp_md PRIVATE "${CTP_SDK_ROOT}")
target_link_libraries(ctp_md PRIVATE
    "-Wl,-l:thostmduserapi_se.so"
    Threads::Threads
    dl
    rt)

set_target_properties(ctp_md PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    BUILD_WITH_INSTALL_RPATH TRUE
    BUILD_RPATH "$ORIGIN"
    INSTALL_RPATH "$ORIGIN")

add_custom_command(TARGET ctp_md POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${CTP_MD_LIBRARY}"
        "$<TARGET_FILE_DIR:ctp_md>/thostmduserapi_se.so"
    VERBATIM)
