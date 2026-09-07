cmake_minimum_required(VERSION 3.16)

project(ctp_market_data_client LANGUAGES CXX)

include(../common/ctp_sdk.cmake)
add_executable(ctp_md src/main.cpp)
configure_ctp_executable(ctp_md)
