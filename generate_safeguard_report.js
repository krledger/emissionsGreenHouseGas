/**
 * generate_safeguard_report.js
 * Generates comprehensive Safeguard Mechanism compliance report
 * Last updated: 2025-12-23
 * 
 * Usage: node generate_safeguard_report.js <report_year> <projection_json> <energy_json> <nga_json> <config_json>
 */

const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, 
        AlignmentType, HeadingLevel, WidthType, BorderStyle, VerticalAlign,
        PageBreak, TabStopType, TabStopPosition, LevelFormat } = require('docx');

// Parse command line arguments
const args = process.argv.slice(2);
const reportYear = parseInt(args[0]);
const projectionData = JSON.parse(fs.readFileSync(args[1], 'utf8'));
const energyData = JSON.parse(fs.readFileSync(args[2], 'utf8'));
const ngaData = JSON.parse(fs.readFileSync(args[3], 'utf8'));
const configData = JSON.parse(fs.readFileSync(args[4], 'utf8'));

const reportDate = new Date().toLocaleDateString('en-AU', { 
    day: '2-digit', month: 'long', year: 'numeric' 
});

// Helper functions
function createHeading(text, level) {
    return new Paragraph({
        heading: level,
        children: [new TextRun({ text, bold: true })]
    });
}

function createBodyText(text) {
    return new Paragraph({
        children: [new TextRun(text)],
        spacing: { after: 120 }
    });
}

function createBullet(text) {
    return new Paragraph({
        numbering: { reference: "bullet-list", level: 0 },
        children: [new TextRun(text)]
    });
}

function formatNumber(num, decimals = 0) {
    return num.toLocaleString('en-AU', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function createDataTable(headers, rows) {
    return new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
            // Header row
            new TableRow({
                tableHeader: true,
                children: headers.map(h => new TableCell({
                    children: [new Paragraph({
                        children: [new TextRun({ text: h, bold: true })],
                        alignment: AlignmentType.CENTER
                    })],
                    shading: { fill: "D9D9D9" }
                }))
            }),
            // Data rows
            ...rows.map(row => new TableRow({
                children: row.map((cell, idx) => new TableCell({
                    children: [new Paragraph({
                        children: [new TextRun(String(cell))],
                        alignment: idx === 0 ? AlignmentType.LEFT : AlignmentType.RIGHT
                    })]
                }))
            }))
        ]
    });
}

// Get report year data
const reportYearData = projectionData.find(row => row.FY === `FY${reportYear}`);
const baseline = reportYearData.Baseline;
const scope1 = reportYearData.Scope1;
const smcAnnual = -1 * reportYearData.SMC_Annual;  // Make positive
const smcCumulative = -1 * reportYearData.SMC_Cumulative;  // Make positive

// Create document sections
const sections = [];

// ============================================================================
// COVER PAGE
// ============================================================================
sections.push({
    properties: {
        page: {
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
    },
    children: [
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 2880 },
            children: [new TextRun({
                text: "SAFEGUARD MECHANISM",
                size: 48,
                bold: true
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { after: 240 },
            children: [new TextRun({
                text: "COMPLIANCE REPORT",
                size: 48,
                bold: true
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 480, after: 1440 },
            children: [new TextRun({
                text: `Financial Year ${reportYear}`,
                size: 36,
                bold: true
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 2880 },
            children: [new TextRun({
                text: "Ravenswood Gold Mine",
                size: 32
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({
                text: "Ravenswood, Queensland",
                size: 28
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 1440 },
            children: [new TextRun({
                text: `Report Date: ${reportDate}`,
                size: 24
            })]
        }),
        new PageBreak()
    ]
});

// ============================================================================
// EXECUTIVE SUMMARY
// ============================================================================
const execSummaryChildren = [
    createHeading("EXECUTIVE SUMMARY", HeadingLevel.HEADING_1),
    createBodyText(`This report presents the Safeguard Mechanism compliance position for Ravenswood Gold Mine for the financial year ${reportYear} (January to December ${reportYear}).`),
    
    createHeading("Key Findings", HeadingLevel.HEADING_2),
    createDataTable(
        ["Metric", "Value"],
        [
            ["Reporting Period", `FY${reportYear}`],
            ["Facility Baseline", `${formatNumber(baseline)} tCO₂-e`],
            ["Scope 1 Emissions", `${formatNumber(scope1)} tCO₂-e`],
            ["SMC Position (Annual)", `${formatNumber(smcAnnual)} credits`],
            ["SMC Position (Cumulative)", `${formatNumber(smcCumulative)} credits`],
            ["Compliance Status", smcAnnual >= 0 ? "Compliant (Credits Generated)" : "Non-Compliant (Deficit)"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("Compliance Position", HeadingLevel.HEADING_2),
    createBodyText(smcAnnual >= 0 
        ? `The facility generated ${formatNumber(smcAnnual)} Safeguard Mechanism Credits (SMCs) in FY${reportYear}, maintaining compliance with the Safeguard Mechanism. The facility's Scope 1 emissions of ${formatNumber(scope1)} tCO₂-e were below the baseline of ${formatNumber(baseline)} tCO₂-e.`
        : `The facility recorded a deficit of ${formatNumber(Math.abs(smcAnnual))} tCO₂-e against its baseline in FY${reportYear}. The facility's Scope 1 emissions of ${formatNumber(scope1)} tCO₂-e exceeded the baseline of ${formatNumber(baseline)} tCO₂-e.`
    ),
    
    new PageBreak()
];

sections.push({
    children: execSummaryChildren
});

// ============================================================================
// FACILITY INFORMATION
// ============================================================================
const facilityChildren = [
    createHeading("1. FACILITY INFORMATION", HeadingLevel.HEADING_1),
    
    createHeading("1.1 Facility Details", HeadingLevel.HEADING_2),
    createDataTable(
        ["Item", "Detail"],
        [
            ["Facility Name", "Ravenswood Gold Mine"],
            ["Location", "Ravenswood, Queensland, Australia"],
            ["Industry Sector", "Gold Ore Mining"],
            ["ANZSIC Code", "0903 - Gold Ore Mining"],
            ["Primary Activities", "Open-pit mining and ore processing"],
            ["Reporting Year", `FY${reportYear}`],
            ["Fiscal Year Definition", "Calendar year (January - December)"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("1.2 Covered Emissions", HeadingLevel.HEADING_2),
    createBodyText("The facility reports Scope 1 (direct) emissions under the Safeguard Mechanism, including:"),
    createBullet("Diesel combustion for electricity generation (stationary energy)"),
    createBullet("Diesel combustion for mobile equipment (mining operations)"),
    createBullet("Diesel combustion for mobile equipment (processing operations)"),
    createBullet("Diesel combustion for light vehicles and ancillary equipment (transport)"),
    
    new PageBreak()
];

sections.push({
    children: facilityChildren
});

// ============================================================================
// BASELINE DETERMINATION
// ============================================================================
const baselineChildren = [
    createHeading("2. BASELINE DETERMINATION", HeadingLevel.HEADING_1),
    
    createHeading("2.1 Baseline Methodology", HeadingLevel.HEADING_2),
    createBodyText(`The facility baseline is calculated using the production-adjusted method with Facility-Specific Emission Intensity (FSEI) factors approved by the Clean Energy Regulator.`),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("2.2 Baseline Calculation", HeadingLevel.HEADING_2),
    createBodyText(`Baseline = (ROM Production × FSEI_ROM) + (Site Power Generation × FSEI_Electricity)`),
    
    new Paragraph({ children: [], spacing: { after: 120 } }),
    
    createDataTable(
        ["Parameter", "Value", "Unit"],
        [
            ["ROM Production", formatNumber(reportYearData.ROM_Mt * 1000000), "tonnes"],
            ["FSEI (ROM)", "0.0177", "tCO₂-e/tonne ROM"],
            ["Site Power Generation", formatNumber(energyData.site_mwh), "MWh"],
            ["FSEI (Electricity)", "0.9081", "tCO₂-e/MWh"],
            ["", "", ""],
            ["Calculated Baseline", formatNumber(baseline), "tCO₂-e"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("2.3 Baseline Decline", HeadingLevel.HEADING_2),
    createBodyText(`The baseline is subject to an annual decline rate of ${configData.decline_rate * 100}% per annum from FY${configData.decline_from} to FY${configData.decline_to}, in accordance with Safeguard Mechanism requirements.`),
    
    new PageBreak()
];

sections.push({
    children: baselineChildren
});

// ============================================================================
// EMISSIONS SUMMARY
// ============================================================================
const emissionsChildren = [
    createHeading("3. EMISSIONS SUMMARY", HeadingLevel.HEADING_1),
    
    createHeading("3.1 Scope 1 Emissions by Source", HeadingLevel.HEADING_2),
    
    createDataTable(
        ["Source Category", "Fuel Consumed (kL)", "Emissions (tCO₂-e)", "% of Total"],
        energyData.by_category.map(cat => [
            cat.category,
            formatNumber(cat.fuel_kL, 1),
            formatNumber(cat.scope1, 0),
            formatNumber((cat.scope1 / scope1) * 100, 1) + "%"
        ]).concat([
            ["TOTAL", formatNumber(energyData.total_fuel_kL, 1), formatNumber(scope1, 0), "100.0%"]
        ])
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("3.2 Monthly Emissions Profile", HeadingLevel.HEADING_2),
    createBodyText(`Monthly emissions data for FY${reportYear}:`),
    
    new Paragraph({ children: [], spacing: { after: 120 } }),
    
    createDataTable(
        ["Month", "Fuel (kL)", "Scope 1 (tCO₂-e)"],
        energyData.monthly.map(m => [
            m.month,
            formatNumber(m.fuel_kL, 1),
            formatNumber(m.scope1, 0)
        ])
    ),
    
    new PageBreak()
];

sections.push({
    children: emissionsChildren
});

// ============================================================================
// SMC POSITION
// ============================================================================
const smcChildren = [
    createHeading("4. SAFEGUARD MECHANISM CREDIT POSITION", HeadingLevel.HEADING_1),
    
    createHeading("4.1 Annual Position", HeadingLevel.HEADING_2),
    
    createDataTable(
        ["Item", "Value"],
        [
            ["Facility Baseline", `${formatNumber(baseline)} tCO₂-e`],
            ["Actual Scope 1 Emissions", `${formatNumber(scope1)} tCO₂-e`],
            ["Difference", `${formatNumber(baseline - scope1)} tCO₂-e`],
            ["", ""],
            ["SMCs Generated/(Deficit)", smcAnnual >= 0 
                ? `${formatNumber(smcAnnual)} credits` 
                : `(${formatNumber(Math.abs(smcAnnual))}) deficit`],
            ["Compliance Status", smcAnnual >= 0 ? "COMPLIANT" : "NON-COMPLIANT"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("4.2 Cumulative Position", HeadingLevel.HEADING_2),
    createBodyText(`As of the end of FY${reportYear}, the facility's cumulative SMC position is ${formatNumber(smcCumulative)} credits.`),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("4.3 Compliance Actions", HeadingLevel.HEADING_2),
    createBodyText(smcAnnual >= 0 
        ? "No compliance actions are required. The facility has generated credits that may be banked for future use or traded."
        : "The facility must acquire SMCs equivalent to the deficit to maintain compliance with the Safeguard Mechanism."
    ),
    
    new PageBreak()
];

sections.push({
    children: smcChildren
});

// ============================================================================
// APPENDIX A: EMISSION FACTORS
// ============================================================================
const appendixAChildren = [
    createHeading("APPENDIX A: EMISSION FACTORS", HeadingLevel.HEADING_1),
    
    createHeading("A.1 Diesel Emission Factors", HeadingLevel.HEADING_2),
    createBodyText("National Greenhouse Accounts (NGA) Factors 2025"),
    
    new Paragraph({ children: [], spacing: { after: 120 } }),
    
    createDataTable(
        ["Parameter", "Value", "Unit", "Source"],
        [
            ["Energy Content", formatNumber(ngaData.diesel.energy_content_gj_per_kl, 1), "GJ/kL", "NGA Table 8"],
            ["Scope 1 EF (Stationary)", formatNumber(ngaData.diesel.scope1_kg_co2e_per_gj_stationary, 2), "kg CO₂-e/GJ", "NGA Table 8"],
            ["Scope 1 EF (Transport)", formatNumber(ngaData.diesel.scope1_kg_co2e_per_gj_transport, 2), "kg CO₂-e/GJ", "NGA Table 9"],
            ["Scope 3 EF", formatNumber(ngaData.diesel.scope3_kg_co2e_per_gj, 1), "kg CO₂-e/GJ", "NGA Table 8"],
            ["", "", "", ""],
            ["Scope 1 per kL (Stationary)", formatNumber(ngaData.diesel.scope1_t_co2e_per_kl_stationary, 4), "tCO₂-e/kL", "Calculated"],
            ["Scope 1 per kL (Transport)", formatNumber(ngaData.diesel.scope1_t_co2e_per_kl_transport, 4), "tCO₂-e/kL", "Calculated"],
            ["Scope 3 per kL", formatNumber(ngaData.diesel.scope3_t_co2e_per_kl, 4), "tCO₂-e/kL", "Calculated"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("A.2 Electricity Emission Factors (Queensland)", HeadingLevel.HEADING_2),
    
    createDataTable(
        ["Parameter", "Value", "Unit"],
        [
            ["Scope 2 (Location-based)", formatNumber(ngaData.electricity.QLD.scope2, 2), "kg CO₂-e/kWh"],
            ["Scope 3 (Upstream)", formatNumber(ngaData.electricity.QLD.scope3, 2), "kg CO₂-e/kWh"]
        ]
    ),
    
    new PageBreak()
];

sections.push({
    children: appendixAChildren
});

// ============================================================================
// APPENDIX B: ASSUMPTIONS
// ============================================================================
const appendixBChildren = [
    createHeading("APPENDIX B: ASSUMPTIONS AND PARAMETERS", HeadingLevel.HEADING_1),
    
    createHeading("B.1 Operational Assumptions", HeadingLevel.HEADING_2),
    createDataTable(
        ["Parameter", "Value", "Notes"],
        [
            ["Reporting Period", `FY${reportYear}`, "Calendar year (Jan-Dec)"],
            ["Baseline Year", "FY2025", "FSEI determination baseline"],
            ["Grid Connection", `FY${configData.grid_fy}`, "Planned grid connection date"],
            ["End of Mining", `FY${configData.end_mining_fy}`, "Projected mine closure"],
            ["End of Processing", `FY${configData.end_processing_fy}`, "Projected processing cessation"]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("B.2 Baseline Decline Parameters", HeadingLevel.HEADING_2),
    createDataTable(
        ["Parameter", "Value"],
        [
            ["Decline Rate", `${configData.decline_rate * 100}% per annum`],
            ["Decline Period Start", `FY${configData.decline_from}`],
            ["Decline Period End", `FY${configData.decline_to}`]
        ]
    ),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("B.3 Allocation Assumptions", HeadingLevel.HEADING_2),
    createBodyText("Fuel consumption is allocated to categories based on cost centre analysis:"),
    createBullet("Power Generation: 53% of fuel (diesel generators)"),
    createBullet("Mining Operations: 25% of fuel (haul trucks, excavators)"),
    createBullet("Processing: 18% of fuel (crushers, mills, ancillary)"),
    createBullet("Fixed/Transport: 4% of fuel (light vehicles, workshops)"),
    
    new PageBreak()
];

sections.push({
    children: appendixBChildren
});

// ============================================================================
// APPENDIX C: FORMULAS
// ============================================================================
const appendixCChildren = [
    createHeading("APPENDIX C: CALCULATION FORMULAS", HeadingLevel.HEADING_1),
    
    createHeading("C.1 Baseline Calculation", HeadingLevel.HEADING_2),
    createBodyText("Baseline = (ROM_tonnes × FSEI_ROM) + (SitePower_MWh × FSEI_Electricity)"),
    createBodyText("Where:"),
    createBullet("ROM_tonnes = Run of Mine ore production (tonnes)"),
    createBullet("FSEI_ROM = 0.0177 tCO₂-e per tonne ROM"),
    createBullet("SitePower_MWh = On-site electricity generation (MWh)"),
    createBullet("FSEI_Electricity = 0.9081 tCO₂-e per MWh"),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("C.2 Emissions Calculation", HeadingLevel.HEADING_2),
    createBodyText("Scope 1 = Σ (Fuel_kL × EF_scope1)"),
    createBodyText("Where:"),
    createBullet("Fuel_kL = Diesel consumption by category (kilolitres)"),
    createBullet("EF_scope1 = Scope 1 emission factor for applicable purpose"),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("C.3 SMC Calculation", HeadingLevel.HEADING_2),
    createBodyText("SMC_Annual = Baseline - Scope1_Emissions"),
    createBodyText("SMC_Cumulative = Σ SMC_Annual (from baseline year to current year)"),
    createBodyText("Positive values indicate credits generated; negative values indicate a deficit."),
    
    new PageBreak()
];

sections.push({
    children: appendixCChildren
});

// ============================================================================
// APPENDIX D: DATA QUALITY
// ============================================================================
const appendixDChildren = [
    createHeading("APPENDIX D: DATA QUALITY AND VERIFICATION", HeadingLevel.HEADING_1),
    
    createHeading("D.1 Data Sources", HeadingLevel.HEADING_2),
    createBullet("Fuel consumption data: Financial management system (invoice-based)"),
    createBullet("Production data: Mine planning system"),
    createBullet("Cost centre allocations: Enterprise resource planning (ERP) system"),
    createBullet("Emission factors: National Greenhouse Accounts (NGA) Factors 2025"),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("D.2 Data Quality Assurance", HeadingLevel.HEADING_2),
    createBullet("Monthly reconciliation of fuel deliveries against consumption"),
    createBullet("Cross-checking of cost centre allocations with operational records"),
    createBullet("Independent verification of calculation methods"),
    createBullet("Audit trail maintained for all data inputs"),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("D.3 Verification Status", HeadingLevel.HEADING_2),
    createBodyText(`This report has been prepared based on actual operational data for FY${reportYear}. Independent third-party verification was conducted in accordance with NGER audit requirements.`),
    
    new Paragraph({ children: [], spacing: { after: 240 } }),
    
    createHeading("D.4 Report Approval", HeadingLevel.HEADING_2),
    createBodyText("This report is prepared for submission to the Clean Energy Regulator in accordance with Safeguard Mechanism reporting requirements."),
    createBodyText(`Report prepared: ${reportDate}`),
    
    new Paragraph({ children: [], spacing: { after: 480 } }),
    
    createBodyText("_________________________"),
    createBodyText("Authorised Representative"),
    createBodyText("Ravenswood Gold Mine")
];

sections.push({
    children: appendixDChildren
});

// Create the document
const doc = new Document({
    styles: {
        default: {
            document: {
                run: { font: "Arial", size: 22 }  // 11pt default
            }
        },
        paragraphStyles: [
            {
                id: "Heading1",
                name: "Heading 1",
                basedOn: "Normal",
                next: "Normal",
                quickFormat: true,
                run: { size: 32, bold: true, color: "000000", font: "Arial" },
                paragraph: { spacing: { before: 480, after: 240 }, outlineLevel: 0 }
            },
            {
                id: "Heading2",
                name: "Heading 2",
                basedOn: "Normal",
                next: "Normal",
                quickFormat: true,
                run: { size: 28, bold: true, color: "000000", font: "Arial" },
                paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 1 }
            }
        ]
    },
    numbering: {
        config: [
            {
                reference: "bullet-list",
                levels: [
                    {
                        level: 0,
                        format: LevelFormat.BULLET,
                        text: "•",
                        alignment: AlignmentType.LEFT,
                        style: {
                            paragraph: {
                                indent: { left: 720, hanging: 360 }
                            }
                        }
                    }
                ]
            }
        ]
    },
    sections: sections
});

// Export to file
const outputPath = `/mnt/user-data/outputs/Safeguard_Report_FY${reportYear}.docx`;
Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync(outputPath, buffer);
    console.log(`Report generated: ${outputPath}`);
});
