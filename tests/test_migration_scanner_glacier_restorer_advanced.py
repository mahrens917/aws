"""Unit tests for glacier restore functions - Advanced operations"""

from unittest import mock

import pytest
from botocore.exceptions import ClientError

from migration_scanner import request_restore
from tests.assertions import assert_equal


class TestGlacierRestorerStorageClassTiers:
    """Test glacier restore storage class tier selection"""

    def test_request_restore_for_glacier(self, s3_mock, state_mock):
        """Test requesting restore for GLACIER storage class"""
        with mock.patch("migration_scanner.GLACIER_RESTORE_TIER", "Standard"):
            with mock.patch("migration_scanner.GLACIER_RESTORE_DAYS", 1):
                file_info = {
                    "bucket": "test-bucket",
                    "key": "file.txt",
                    "storage_class": "GLACIER",
                }

                request_restore(s3_mock, state_mock, file_info, 1, 1)

                # Should use configured tier for GLACIER
                call_args = s3_mock.restore_object.call_args
                assert call_args[1]["RestoreRequest"]["GlacierJobParameters"]["Tier"] == "Standard"

    def test_request_restore_for_deep_archive(self, s3_mock, state_mock):
        """Test requesting restore for DEEP_ARCHIVE uses Bulk tier"""
        with mock.patch("migration_scanner.GLACIER_RESTORE_DAYS", 1):
            file_info = {
                "bucket": "test-bucket",
                "key": "file.txt",
                "storage_class": "DEEP_ARCHIVE",
            }

            request_restore(s3_mock, state_mock, file_info, 1, 1)

            # Should use Bulk tier for DEEP_ARCHIVE
            call_args = s3_mock.restore_object.call_args
            assert call_args[1]["RestoreRequest"]["GlacierJobParameters"]["Tier"] == "Bulk"


class TestGlacierRestorerErrorHandling:
    """Test glacier restore error handling"""

    def test_request_restore_already_in_progress(self, s3_mock, state_mock):
        """Test handling RestoreAlreadyInProgress error"""
        error_response = {
            "Error": {
                "Code": "RestoreAlreadyInProgress",
                "Message": "Already restoring",
            }
        }
        s3_mock.restore_object.side_effect = ClientError(error_response, "RestoreObject")

        file_info = {
            "bucket": "test-bucket",
            "key": "file.txt",
            "storage_class": "GLACIER",
        }

        # Should not raise, should mark as requested
        request_restore(s3_mock, state_mock, file_info, 1, 1)

        state_mock.mark_glacier_restore_requested.assert_called_once()

    def test_request_restore_other_error(self, s3_mock):
        """Test that other errors are raised"""
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        s3_mock.restore_object.side_effect = ClientError(error_response, "RestoreObject")

        file_info = {
            "bucket": "test-bucket",
            "key": "file.txt",
            "storage_class": "GLACIER",
        }

        # Should raise because it's not RestoreAlreadyInProgress
        with pytest.raises(ClientError):
            request_restore(s3_mock, mock.Mock(), file_info, 1, 1)


def test_request_restore_uses_correct_config_values(s3_mock, state_mock):
    """Test that restore request uses config values"""
    with mock.patch("migration_scanner.GLACIER_RESTORE_TIER", "Expedited"):
        with mock.patch("migration_scanner.GLACIER_RESTORE_DAYS", 5):
            file_info = {
                "bucket": "test-bucket",
                "key": "file.txt",
                "storage_class": "GLACIER",
            }

            request_restore(s3_mock, state_mock, file_info, 1, 1)

            call_args = s3_mock.restore_object.call_args
            restore_request = call_args[1]["RestoreRequest"]
            assert_equal(restore_request["Days"], 5)
            assert restore_request["GlacierJobParameters"]["Tier"] == "Expedited"
