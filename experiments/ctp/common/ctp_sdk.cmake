set(CTP_COMMON_DIR "${CMAKE_CURRENT_LIST_DIR}")
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "This target requires native Linux")
endif()

if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "The bundled CTP SDK requires Linux x86-64")
endif()

set(CTP_SDK_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/../sdk/v6.7.13_20260225/linux64/mdapi"
    CACHE PATH "Path to the bundled CTP Linux market-data SDK")

set(CTP_LINK_MODE "AUTO" CACHE STRING
    "CTP SDK link mode: AUTO prefers a static archive, STATIC requires one, SHARED uses the shared object")
set_property(CACHE CTP_LINK_MODE PROPERTY STRINGS AUTO STATIC SHARED)
string(TOUPPER "${CTP_LINK_MODE}" CTP_LINK_MODE)

if(NOT CTP_LINK_MODE MATCHES "^(AUTO|STATIC|SHARED)$")
    message(FATAL_ERROR "CTP_LINK_MODE must be AUTO, STATIC, or SHARED")
endif()

set(CTP_MD_HEADERS
    "${CTP_SDK_ROOT}/ThostFtdcMdApi.h"
    "${CTP_SDK_ROOT}/ThostFtdcUserApiDataType.h"
    "${CTP_SDK_ROOT}/ThostFtdcUserApiStruct.h")
foreach(header_path IN LISTS CTP_MD_HEADERS)
    if(NOT EXISTS "${header_path}")
        message(FATAL_ERROR "Required CTP SDK header is missing: ${header_path}")
    endif()
endforeach()

set(CTP_MD_STATIC_LIBRARY "")
foreach(static_name IN ITEMS thostmduserapi_se.a libthostmduserapi_se.a)
    if(EXISTS "${CTP_SDK_ROOT}/${static_name}")
        set(CTP_MD_STATIC_LIBRARY "${CTP_SDK_ROOT}/${static_name}")
        break()
    endif()
endforeach()
set(CTP_MD_SHARED_LIBRARY "${CTP_SDK_ROOT}/thostmduserapi_se.so")

if(CTP_LINK_MODE STREQUAL "STATIC")
    if(NOT CTP_MD_STATIC_LIBRARY)
        message(FATAL_ERROR
            "CTP_LINK_MODE=STATIC was requested, but the official SDK contains no static archive. "
            "Expected thostmduserapi_se.a or libthostmduserapi_se.a under ${CTP_SDK_ROOT}.")
    endif()
    set(CTP_MD_LIBRARY "${CTP_MD_STATIC_LIBRARY}")
    set(CTP_EFFECTIVE_LINK_MODE "STATIC")
elseif(CTP_LINK_MODE STREQUAL "SHARED")
    if(NOT EXISTS "${CTP_MD_SHARED_LIBRARY}")
        message(FATAL_ERROR "Required CTP shared library is missing: ${CTP_MD_SHARED_LIBRARY}")
    endif()
    set(CTP_MD_LIBRARY "${CTP_MD_SHARED_LIBRARY}")
    set(CTP_EFFECTIVE_LINK_MODE "SHARED")
elseif(CTP_MD_STATIC_LIBRARY)
    set(CTP_MD_LIBRARY "${CTP_MD_STATIC_LIBRARY}")
    set(CTP_EFFECTIVE_LINK_MODE "STATIC")
else()
    if(NOT EXISTS "${CTP_MD_SHARED_LIBRARY}")
        message(FATAL_ERROR
            "No usable CTP market-data library found under ${CTP_SDK_ROOT}. "
            "Expected a static archive or thostmduserapi_se.so.")
    endif()
    set(CTP_MD_LIBRARY "${CTP_MD_SHARED_LIBRARY}")
    set(CTP_EFFECTIVE_LINK_MODE "SHARED")
endif()

message(STATUS "CTP SDK link mode: ${CTP_EFFECTIVE_LINK_MODE} (${CTP_MD_LIBRARY})")

find_package(Threads REQUIRED)

if(CTP_EFFECTIVE_LINK_MODE STREQUAL "STATIC")
    add_library(ctp_md_sdk UNKNOWN IMPORTED)
    set_target_properties(ctp_md_sdk PROPERTIES
        IMPORTED_LOCATION "${CTP_MD_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${CTP_SDK_ROOT}")
else()
    add_library(ctp_md_sdk INTERFACE)
    target_include_directories(ctp_md_sdk SYSTEM INTERFACE "${CTP_SDK_ROOT}")
    target_link_directories(ctp_md_sdk INTERFACE "${CTP_SDK_ROOT}")
    target_link_libraries(ctp_md_sdk INTERFACE "-Wl,-l:thostmduserapi_se.so")
endif()

function(configure_ctp_executable target)
    target_compile_features(${target} PRIVATE cxx_std_17)
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    target_link_libraries(${target} PRIVATE ctp_md_sdk Threads::Threads dl rt)
    target_include_directories(${target} PRIVATE "${CTP_COMMON_DIR}")
    set_target_properties(${target} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    if(CTP_EFFECTIVE_LINK_MODE STREQUAL "SHARED")
        set_target_properties(${target} PROPERTIES BUILD_WITH_INSTALL_RPATH TRUE BUILD_RPATH "$ORIGIN" INSTALL_RPATH "$ORIGIN")
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${CTP_MD_SHARED_LIBRARY}" "$<TARGET_FILE_DIR:${target}>/thostmduserapi_se.so" VERBATIM)
    endif()
endfunction()
