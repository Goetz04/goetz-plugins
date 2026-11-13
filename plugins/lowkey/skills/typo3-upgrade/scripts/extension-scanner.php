<?php

declare(strict_types=1);

/**
 * Runs the TYPO3 Extension Scanner (same matchers as Admin Tools > Upgrade) on one extension.
 * The scanner only knows the matchers of the installed core. Run it again after every Composer jump.
 *
 * Usage:   ddev exec php .typo3-upgrade/tools/extension-scanner.php <extension-key>
 * Env:     TYPO3_UPGRADE_AUTOLOAD overrides the autoloader path (default: ./vendor/autoload.php).
 * Output:  One line per match as "<indicator> <relative path>:<line> <message>",
 *          one "ERROR <relative path>: <reason>" line per unreadable or unparsable file,
 *          and a last line "TOTAL strong=<n> weak=<n> errors=<n>".
 * Exit:    0 scanned completely without strong match, 1 at least one strong match,
 *          2 setup or runtime error or incomplete scan (errors > 0 in the TOTAL line).
 * Support: CLI tested on TYPO3 12 and 13. On TYPO3 11 the capability probe decides.
 */

use PhpParser\Error as ParserError;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitor\NameResolver;
use PhpParser\Parser;
use PhpParser\ParserFactory;
use TYPO3\CMS\Core\Core\Bootstrap;
use TYPO3\CMS\Core\Core\SystemEnvironmentBuilder;
use TYPO3\CMS\Core\Utility\ExtensionManagementUtility;
use TYPO3\CMS\Install\Controller\UpgradeController;
use TYPO3\CMS\Install\ExtensionScanner\Php\GeneratorClassesResolver;
use TYPO3\CMS\Install\ExtensionScanner\Php\MatcherFactory;

const SCRIPT_NAME = 'extension-scanner.php';

function fail(string $message): void
{
    fwrite(STDERR, SCRIPT_NAME . ': ' . $message . PHP_EOL);
    exit(2);
}

function resolveAutoloadPath(): string
{
    $configured = getenv('TYPO3_UPGRADE_AUTOLOAD');
    if (is_string($configured) && $configured !== '') {
        return $configured;
    }
    $cwd = getcwd();
    return ($cwd === false ? '.' : $cwd) . '/vendor/autoload.php';
}

function createParser(): Parser
{
    if (method_exists(ParserFactory::class, 'createForNewestSupportedVersion')) {
        return (new ParserFactory())->createForNewestSupportedVersion();
    }
    return (new ParserFactory())->create(ParserFactory::PREFER_PHP7);
}

/**
 * @return array<int, string> sorted absolute paths of the PHP files of the extension
 */
function collectPhpFiles(string $basePath): array
{
    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($basePath, FilesystemIterator::SKIP_DOTS)
    );
    $paths = [];
    foreach ($iterator as $file) {
        if (!$file instanceof SplFileInfo || !preg_match('/\.php$/', $file->getPathname())) {
            continue;
        }
        $relative = '/' . ltrim(substr($file->getPathname(), strlen($basePath)), '/');
        foreach (['/vendor/', '/node_modules/', '/.Build/'] as $skipped) {
            if (strpos($relative, $skipped) !== false) {
                continue 2;
            }
        }
        $paths[] = $file->getPathname();
    }
    sort($paths);
    return $paths;
}

$extension = $argv[1] ?? '';
if (preg_match('/^[a-z0-9_]+$/', $extension) !== 1) {
    fwrite(STDERR, 'Usage: php extension-scanner.php <extension-key>' . PHP_EOL);
    fwrite(STDERR, 'The extension key holds lowercase letters, digits and underscores.' . PHP_EOL);
    exit(2);
}

$autoload = resolveAutoloadPath();
if (!is_file($autoload)) {
    fail('autoload not found at ' . $autoload . '. Run from the project root inside the container or set TYPO3_UPGRADE_AUTOLOAD.');
}
$classLoader = require $autoload;

$scannerAvailable = true;
foreach ([
    UpgradeController::class,
    MatcherFactory::class,
    GeneratorClassesResolver::class,
    ParserFactory::class,
    NodeTraverser::class,
    NameResolver::class,
] as $requiredClass) {
    if (!class_exists($requiredClass)) {
        $scannerAvailable = false;
    }
}
if ($scannerAvailable) {
    $defaults = (new ReflectionClass(UpgradeController::class))->getDefaultProperties();
    $scannerAvailable = array_key_exists('matchers', $defaults);
}
if (!$scannerAvailable) {
    fail('Extension Scanner CLI not available here. Use Admin Tools > Upgrade > Scan Extension Files.');
}

try {
    SystemEnvironmentBuilder::run(0, SystemEnvironmentBuilder::REQUESTTYPE_CLI);
    Bootstrap::init($classLoader);

    if (!ExtensionManagementUtility::isLoaded($extension)) {
        fail('extension "' . $extension . '" is not loaded.');
    }
    $basePath = ExtensionManagementUtility::extPath($extension);
    $matcherConfiguration = $defaults['matchers'];
    $parser = createParser();
    $total = ['strong' => 0, 'weak' => 0];
    $errors = 0;

    foreach (collectPhpFiles($basePath) as $path) {
        $relative = substr($path, strlen($basePath));
        $code = file_get_contents($path);
        if ($code === false) {
            printf("ERROR %s: unreadable\n", $relative);
            $errors++;
            continue;
        }
        try {
            $statements = $parser->parse($code) ?? [];
            $traverser = new NodeTraverser();
            $traverser->addVisitor(new NameResolver());
            $statements = $traverser->traverse($statements);
            $traverser = new NodeTraverser();
            $traverser->addVisitor(new GeneratorClassesResolver());
            $matchers = (new MatcherFactory())->createAll($matcherConfiguration);
            foreach ($matchers as $matcher) {
                $traverser->addVisitor($matcher);
            }
            $traverser->traverse($statements);
        } catch (ParserError $e) {
            printf("ERROR %s: %s\n", $relative, $e->getMessage());
            $errors++;
            continue;
        }
        foreach ($matchers as $matcher) {
            foreach ($matcher->getMatches() as $match) {
                $total[$match['indicator']]++;
                printf(
                    "%s %s:%d %s\n",
                    $match['indicator'],
                    $relative,
                    $match['line'],
                    $match['message']
                );
            }
        }
    }
    printf("TOTAL strong=%d weak=%d errors=%d\n", $total['strong'], $total['weak'], $errors);
    if ($errors > 0) {
        exit(2);
    }
    exit($total['strong'] > 0 ? 1 : 0);
} catch (\Throwable $e) {
    fwrite(STDERR, 'extension-scanner.php: ' . get_class($e) . ': ' . $e->getMessage() . PHP_EOL);
    exit(2);
}
