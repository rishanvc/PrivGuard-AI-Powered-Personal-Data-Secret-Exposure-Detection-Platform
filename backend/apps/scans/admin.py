"""Scans are deliberately NOT registered in the Django admin.

The admin lets any staff account browse every row of a registered model.
Scan inventories describe users' sensitive files, so registering them here
would be a back door around D-009 (least privilege: administrators cannot open
other users' scans). Deleting a scan through the admin would also skip removing
its stored files from disk; scans are deleted only through services.delete_scan.
"""
