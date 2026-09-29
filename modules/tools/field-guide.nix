{ ... }:
{
  # Keep the quick reference in the immutable guest image for offline use.
  environment.etc."rednix/field-guide".source = ../../docs/field-guide;
}
