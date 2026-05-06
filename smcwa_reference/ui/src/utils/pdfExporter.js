import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import logoSmc from '../assets/logo-smc.png';

/**
 * Generates a branded PDF report by capturing individual charts
 * 
 * @param {HTMLElement} rootElement - The container element (used to find children)
 * @param {Object} metadata - Metadata to display in the header
 * @param {string} metadata.title - Report title
 * @param {string} metadata.serverName - Server Name
 * @param {string} metadata.serverIp - Server IP
 * @param {string} metadata.startDate - Start Date
 * @param {string} metadata.endDate - End Date
 */
export const exportToPDF = async (rootElement, metadata) => {
  if (!rootElement) {
    console.error("Export to PDF: Element not found");
    return;
  }

  try {
    // Initialize PDF
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margins = { top: 20, left: 15, right: 15, bottom: 20 };
    const contentWidth = pageWidth - margins.left - margins.right;

    let currentY = margins.top;

    // --- Helper: Add Header ---
    const addHeader = () => {
        // Logo
        try {
            pdf.addImage(logoSmc, 'PNG', margins.left, 10, 30, 15);
        } catch (e) {
            pdf.setFontSize(16);
            pdf.setFont('helvetica', 'bold');
            pdf.text("SMC", margins.left, 20);
        }

        // Title
        pdf.setFontSize(18);
        pdf.setFont('helvetica', 'bold');
        pdf.setTextColor(33, 150, 243); // SMC Blue
        pdf.text(metadata.title || "Performance Report", pageWidth - margins.right, 20, { align: 'right' });
        
        return 35; // New Y position
    };

    // --- Helper: Add Footer ---
    const addFooter = (pageNumber, totalPages) => {
        pdf.setPage(pageNumber);
        pdf.setFontSize(8);
        pdf.setTextColor(150);
        pdf.text(
            `Page ${pageNumber} of ${totalPages} - Confidential - SMC LAMA Monitoring`,
            pageWidth / 2,
            pageHeight - 10,
            { align: 'center' }
        );
    };

    // --- 1. Draw First Page Header & Metadata ---
    currentY = addHeader();

    // Metadata Box
    pdf.setFillColor(245, 245, 245);
    pdf.setDrawColor(220, 220, 220);
    pdf.rect(margins.left, currentY, contentWidth, 35, 'FD');

    const textX = margins.left + 5;
    const valueX = margins.left + 45;
    let textY = currentY + 8;
    const lineHeight = 7;

    pdf.setFontSize(10);
    pdf.setTextColor(60, 60, 60);

    // Row 1
    pdf.setFont('helvetica', 'bold');
    pdf.text("Server Name:", textX, textY);
    pdf.setFont('helvetica', 'normal');
    pdf.text(metadata.serverName || "N/A", valueX, textY);

    pdf.setFont('helvetica', 'bold');
    pdf.text("IP Address:", textX + 80, textY);
    pdf.setFont('helvetica', 'normal');
    pdf.text(metadata.serverIp || "N/A", valueX + 80, textY);

    textY += lineHeight;

    // Row 2
    pdf.setFont('helvetica', 'bold');
    pdf.text("Report Range:", textX, textY);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`${metadata.startDate} to ${metadata.endDate}`, valueX, textY);

    textY += lineHeight;

    // Row 3
    pdf.setFont('helvetica', 'bold');
    pdf.text("Generated On:", textX, textY);
    pdf.setFont('helvetica', 'normal');
    pdf.text(new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }), valueX, textY);

    currentY += 45; // Move past metadata

    // --- 2. Find and Capture Charts ---
    // Look for elements with class 'printable-chart'
    const chartElements = Array.from(rootElement.querySelectorAll('.printable-chart'));
    
    console.log(`PDF Export: Found ${chartElements.length} printable charts`);

    if (chartElements.length === 0) {
        console.warn("No .printable-chart elements found. Attempting whole root capture.");
        // Fallback: If no charts found, capture the root itself (less ideal but prevents empty PDF)
        const canvas = await html2canvas(rootElement, { scale: 1.5, useCORS: true });
        const imgData = canvas.toDataURL('image/png');
        pdf.addImage(imgData, 'PNG', margins.left, currentY, contentWidth, 150);
    } else {
        for (let i = 0; i < chartElements.length; i++) {
            const element = chartElements[i];
            
            try {
                // Capture individual chart
                const canvas = await html2canvas(element, {
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    backgroundColor: '#ffffff'
                });

                const imgData = canvas.toDataURL('image/png');
                const imgProps = pdf.getImageProperties(imgData);
                const pdfImgHeight = (imgProps.height * contentWidth) / imgProps.width;

                // Check if fits on current page
                if (currentY + pdfImgHeight > pageHeight - margins.bottom) {
                    pdf.addPage();
                    currentY = margins.top;
                }

                pdf.addImage(imgData, 'PNG', margins.left, currentY, contentWidth, pdfImgHeight);
                currentY += pdfImgHeight + 10;
            } catch (chartErr) {
                console.error(`Failed to capture chart ${i}:`, chartErr);
                pdf.text(`[Error capturing chart ${i+1}]`, margins.left, currentY);
                currentY += 10;
            }
        }
    }

    // --- 3. Add Footers ---
    const pageCount = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
        addFooter(i, pageCount);
    }

    // --- 4. Save ---
    const fileName = `Report_${metadata.serverName}_${new Date().toISOString().slice(0, 10)}.pdf`;
    pdf.save(fileName);

  } catch (error) {
    console.error("Failed to export PDF:", error);
    alert("Failed to generate PDF report. Please try again.");
  }
};