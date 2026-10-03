# Security

ShapeLoop-CAD is intended to run on a trusted local machine. Bind to loopback and keep the session token private. Exposing the service to a network requires a separate authenticated deployment review; the default installation is not a hosted multi-user CAD service.

State-changing API requests require the local session token and an allowed origin. Provider keys stay in the backend configuration file and are excluded from public settings. Prefer HTTPS for remote compatible endpoints; plain HTTP is supported only for loopback inference. Provider errors do not echo response bodies or credentials.

Design data is validated before dispatch. Dimension expressions use a restricted parser. The application generates geometry from the supported semantic model rather than executing model-supplied Python. Build and verification run in limited subprocesses. Imported geometry still exercises native CAD parsers and should be treated as untrusted input; use files from trusted sources and keep native dependencies updated through a tested lock revision.

SolutionScout is limited to official CAD documentation and CadQuery/OCP repository paths. It checks redirects, bounds downloads, ignores proxy environment configuration, and never executes downloaded instructions. Private error text, feature graphs, and component dimensions are not sent as search queries. Optional provider reasoning receives public source evidence by default; sending private investigation context requires explicit `allow_private_query` authorization. Scout cards cannot accept or silently edit the active design.

The local data directory contains designs, proposals, caches, exports, and logs. Back it up as private user data. Provider configuration is written with restrictive file permissions. Deleting the directory removes its history; export useful work before storage cleanup.

For a vulnerability report, use the repository's private reporting channel if one has been configured. Otherwise contact its maintainer without posting credentials, private geometry, or exploit details publicly. This checkout does not prescribe an unverified maintainer email address.
