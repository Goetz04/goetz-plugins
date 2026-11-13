<?php

declare(strict_types=1);

/**
 * Dumps page TSconfig and frontend TypoScript of one page as sorted flat lines.
 * Compare two dumps (before and after a refactoring) to prove equality.
 *
 * Usage:   ddev exec php .typo3-upgrade/tools/ts-dump.php [page-uid] > dump.txt
 *          The page uid defaults to 1.
 * Env:     TYPO3_UPGRADE_AUTOLOAD overrides the autoloader path (default: ./vendor/autoload.php).
 * Output:  Sorted lines with the prefixes TSCONFIG:, SETUP:, CONSTANTS: and SETUPSUB:.
 *          Newlines in values appear as \n. All condition branches stay in, no verdicts are evaluated.
 * Exit:    0 dump written, 2 setup or runtime error.
 * Support: Used on TYPO3 12 and 13, unverified on 14. TYPO3 11 lacks the include tree API.
 */

use TYPO3\CMS\Backend\Utility\BackendUtility;
use TYPO3\CMS\Core\Core\Bootstrap;
use TYPO3\CMS\Core\Core\SystemEnvironmentBuilder;
use TYPO3\CMS\Core\Site\SiteFinder;
use TYPO3\CMS\Core\TypoScript\IncludeTree\SysTemplateRepository;
use TYPO3\CMS\Core\TypoScript\IncludeTree\SysTemplateTreeBuilder;
use TYPO3\CMS\Core\TypoScript\IncludeTree\Traverser\IncludeTreeTraverser;
use TYPO3\CMS\Core\TypoScript\IncludeTree\Visitor\IncludeTreeAstBuilderVisitor;
use TYPO3\CMS\Core\TypoScript\Tokenizer\LosslessTokenizer;
use TYPO3\CMS\Core\Utility\GeneralUtility;
use TYPO3\CMS\Core\Utility\RootlineUtility;

const SCRIPT_NAME = 'ts-dump.php';

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

/**
 * @param array<int|string, mixed> $a
 * @param array<int, string> $out
 */
function flatten(array $a, string $prefix, array &$out): void
{
    foreach ($a as $k => $v) {
        if (is_array($v)) {
            flatten($v, $prefix . $k, $out);
        } else {
            $out[] = $prefix . $k . '=' . str_replace("\n", '\n', (string)$v);
        }
    }
}

$pageArgument = $argv[1] ?? '1';
if (preg_match('/^[1-9][0-9]*$/', $pageArgument) !== 1) {
    fail('invalid page uid "' . $pageArgument . '". Usage: php ts-dump.php [page-uid]');
}
$pageUid = (int)$pageArgument;

$autoload = resolveAutoloadPath();
if (!is_file($autoload)) {
    fail('autoload not found at ' . $autoload . '. Run from the project root inside the container or set TYPO3_UPGRADE_AUTOLOAD.');
}
$classLoader = require $autoload;

foreach ([
    SysTemplateTreeBuilder::class,
    SysTemplateRepository::class,
    IncludeTreeTraverser::class,
    IncludeTreeAstBuilderVisitor::class,
    LosslessTokenizer::class,
] as $requiredClass) {
    if (!class_exists($requiredClass)) {
        fail('needs the TypoScript include tree API of TYPO3 12 or newer. On TYPO3 11 use crawl diffs as TypoScript proof.');
    }
}

try {
    SystemEnvironmentBuilder::run(0, SystemEnvironmentBuilder::REQUESTTYPE_CLI);
    Bootstrap::init($classLoader);
    Bootstrap::initializeBackendUser(\TYPO3\CMS\Core\Authentication\CommandLineUserAuthentication::class);
    Bootstrap::initializeBackendAuthentication();

    $out = [];
    flatten(BackendUtility::getPagesTSconfig($pageUid), 'TSCONFIG:', $out);

    // Frontend TypoScript setup of the page, all condition branches included (no verdicts evaluated).
    $rootline = GeneralUtility::makeInstance(RootlineUtility::class, $pageUid)->get();
    $rows = GeneralUtility::makeInstance(SysTemplateRepository::class)->getSysTemplateRowsByRootline($rootline);
    $site = GeneralUtility::makeInstance(SiteFinder::class)->getSiteByPageId($pageUid);
    $treeBuilder = GeneralUtility::makeInstance(SysTemplateTreeBuilder::class);
    $includeTree = $treeBuilder->getTreeBySysTemplateRowsAndSite('setup', $rows, new LosslessTokenizer(), $site);
    $visitor = GeneralUtility::makeInstance(IncludeTreeAstBuilderVisitor::class);
    (new IncludeTreeTraverser())->traverse($includeTree, [$visitor]);
    flatten($visitor->getAst()->toArray(), 'SETUP:', $out);

    // Constants tree (sys_template constants or site settings + set constants), and setup with constants substituted.
    $constantsTree = $treeBuilder->getTreeBySysTemplateRowsAndSite('constants', $rows, new LosslessTokenizer(), $site);
    $constantsVisitor = GeneralUtility::makeInstance(IncludeTreeAstBuilderVisitor::class);
    (new IncludeTreeTraverser())->traverse($constantsTree, [$constantsVisitor]);
    $flatConstants = $constantsVisitor->getAst()->flatten();
    foreach ($flatConstants as $key => $value) {
        $out[] = 'CONSTANTS:' . $key . '=' . str_replace("\n", '\\n', (string)$value);
    }
    $substVisitor = GeneralUtility::makeInstance(IncludeTreeAstBuilderVisitor::class);
    $substVisitor->setFlatConstants($flatConstants);
    (new IncludeTreeTraverser())->traverse($includeTree, [$substVisitor]);
    flatten($substVisitor->getAst()->toArray(), 'SETUPSUB:', $out);
    sort($out);
    echo implode("\n", $out), "\n";
} catch (\Throwable $e) {
    fwrite(STDERR, 'ts-dump.php: ' . get_class($e) . ': ' . $e->getMessage() . PHP_EOL);
    exit(2);
}
exit(0);
